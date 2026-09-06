import socket
from datetime import datetime


DEVICE_IP = "192.168.1.224"
DEVICE_PORT = 5005
TIMEOUT = 10


FRAMES = {
    "init": bytes.fromhex(
        "55 aa 01 80 00 00 00 00 6f 6e ff ff 00 00 01 00"
    ),
    "info_1": bytes.fromhex(
        "55 aa 01 13 00 00 00 00 00 00 00 00 30 00 02 00"
    ),
    "info_2": bytes.fromhex(
        "55 aa 01 13 01 00 00 00 00 00 00 00 00 04 03 00"
    ),
    "info_3": bytes.fromhex(
        "55 aa 01 13 01 00 00 00 00 01 00 00 04 04 00"
    ),
    "info_4": bytes.fromhex(
        "55 aa 01 13 00 00 00 00 00 00 00 00 30 00 05 00"
    ),
    "cmd_81": bytes.fromhex(
        "55 aa 01 81 00 00 00 00 00 00 ff ff 00 00 06 00"
    ),
    "cmd_b4": bytes.fromhex(
        "55 aa 01 b4 08 00 00 00 00 00 ff ff 00 00 07 00"
    ),
    "finish_81": bytes.fromhex(
        "55 aa 01 81 01 00 00 00 00 00 ff ff 00 00 0a 00"
    ),
}


def decode_timestamp(raw):
    """Decode the Secureye packed 4-byte timestamp."""
    if len(raw) != 4:
        return None

    value = int.from_bytes(raw, "little")

    minute = (value >> 26) & 0x3F
    hour = (value >> 21) & 0x1F
    day = (value >> 16) & 0x1F
    month = (value >> 12) & 0x0F
    year = (value & 0x0FFF) + 1521

    try:
        return datetime(year, month, day, hour, minute)
    except ValueError:
        return None


class SecureyeTester:
    def __init__(self, host=DEVICE_IP, port=DEVICE_PORT, timeout=TIMEOUT):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = None

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect((self.host, self.port))
        print(f"Connected to {self.host}:{self.port}")

    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None

    def recv_until_quiet(self, quiet=2.0):
        old_timeout = self.sock.gettimeout()
        self.sock.settimeout(quiet)

        data = bytearray()

        try:
            while True:
                try:
                    chunk = self.sock.recv(4096)
                    if not chunk:
                        break
                    data.extend(chunk)
                except socket.timeout:
                    break
        finally:
            self.sock.settimeout(old_timeout)

        return bytes(data)

    def command(self, name):
        frame = FRAMES[name]

        print("\n" + "=" * 80)
        print(f"TX [{name}]")
        print("=" * 80)
        print(frame.hex(" "))

        self.sock.sendall(frame)
        response = self.recv_until_quiet()

        print(f"RX [{name}] ({len(response)} bytes)")
        if response:
            print(response.hex(" "))

        return response

    def initialize(self):
        self.command("init")
        self.command("info_1")
        self.command("info_2")
        self.command("info_3")
        self.command("info_4")
        self.command("cmd_81")

    def get_record_count(self):
        response = self.command("cmd_b4")

        if len(response) < 6:
            raise ValueError("Invalid B4 response")

        # Attendance count is a 16-bit little-endian value
        # at response bytes 4-5.
        #
        # Example:
        #
        #     04 01
        #
        # = 0x0104
        # = 260 records

        count = int.from_bytes(response[4:6], "little")

        print(
            f"\nDevice reports {count} attendance records "
            f"(raw count: {response[4:6].hex(' ')})"
        )

        return count

    @staticmethod
    def make_a4_first_request(count):
        # Actual OnTime first A4 request:
        # 55 aa 01 a4 00 00 00 00
        # <record count, 4 bytes LE>
        # 00 04 08 00
        return (
            bytes.fromhex("55 aa 01 a4 00 00 00 00")
            + count.to_bytes(4, "little")
            + bytes.fromhex("00 04 08 00")
        )

    @staticmethod
    def make_a4_continuation_request(block_index, request_length):
        """
        Build an A4 continuation request.

        Observed OnTime / Secureye pattern:

            Block 1:
            ... 00 00 01 00 <length LE> 09 00

            Block 2:
            ... 00 00 02 00 <length LE> 0A 00
        """

        if block_index < 1:
            raise ValueError("Continuation block_index must be >= 1")

        if request_length <= 0:
            raise ValueError("request_length must be > 0")

        if request_length > 0xFFFF:
            raise ValueError("request_length is too large")

        stage = 8 + block_index

        return (
            bytes.fromhex("55 aa 01 a4 00 00 00 00")
            + b"\x00\x00"
            + block_index.to_bytes(2, "little")
            + request_length.to_bytes(2, "little")
            + stage.to_bytes(2, "little")
        )

    def send_a4(self, request, label):
        print("\n" + "-" * 80)
        print(label)
        print("-" * 80)
        print("TX:", request.hex(" "))

        self.sock.sendall(request)
        response = self.recv_until_quiet()

        print("RX length:", len(response))

        if len(response) < 14:
            raise ValueError(
                f"{label}: response too short ({len(response)} bytes)"
            )

        if response[10:12] != b"\x55\xaa":
            raise ValueError(
                f"{label}: missing A4 payload marker at response[10:12]"
            )

        return response

    @staticmethod
    def extract_a4_data(response, keep_final_terminator=False):
        """
        A4 response:
            bytes 0..9   = outer response header
            bytes 10..11 = 55 aa marker
            bytes 12..   = A4 data

        Each observed response ends with 00 00.

        For A4 #1 that terminator is block framing and is removed.

        For A4 #2 we keep its final 00 00 because the known final
        attendance fragment is 10 bytes. The final fragment therefore
        consists of 8 data bytes + the final 00 00.
        """
        data = response[12:]

        if len(data) < 2:
            raise ValueError("A4 response contains no data")

        if data[-2:] != b"\x00\x00":
            raise ValueError(
                "A4 response does not end with expected 00 00 terminator"
            )

        if keep_final_terminator:
            return data

        return data[:-2]

    def get_logs_raw(self, count):
        if count <= 0:
            return b"", None

        print("\n" + "=" * 80)
        print("A4 ATTENDANCE DOWNLOAD")
        print("=" * 80)

        # ---------------------------------------------------------
        # Secureye attendance data layout
        #
        # 4 bytes  = first card ID
        # 12 bytes = each normal attendance record
        # 8 bytes  = final attendance record data
        #
        # Therefore the requested A4 data size is:
        #
        #     4 + ((count - 1) * 12) + 8
        #
        # which equals count * 12.
        # ---------------------------------------------------------

        total_data_length = count * 12

        print(f"Record count          : {count}")
        print(f"Expected A4 data     : {total_data_length} bytes")

        blocks = []
        remaining = total_data_length
        block_index = 0

        # =========================================================
        # A4 BLOCK LOOP
        # =========================================================

        while remaining > 0:

            if block_index == 0:
                request_length = min(1024, remaining)

                request = self.make_a4_first_request(count)

            else:
                # Every continuation block is MAX 1024 bytes.
                request_length = min(1024, remaining)

                request = self.make_a4_continuation_request(
                    block_index,
                    request_length,
                )

            label = f"A4 #{block_index + 1}"

            response = self.send_a4(request, label)

            # -----------------------------------------------------
            # Extract exactly the bytes requested by this A4 block.
            #
            # The response itself contains an additional 00 00
            # terminator after the requested data.
            # -----------------------------------------------------

            raw_data = response[12:]

            expected_response_data = request_length + 2

            if len(raw_data) != expected_response_data:
                raise ValueError(
                    f"{label}: unexpected response data size: "
                    f"received {len(raw_data)}, "
                    f"expected {expected_response_data} "
                    f"(requested {request_length} + terminator)"
                )

            if raw_data[-2:] != b"\x00\x00":
                raise ValueError(
                    f"{label}: missing 00 00 response terminator"
                )

            block_data = raw_data[:-2]

            if len(block_data) != request_length:
                raise ValueError(
                    f"{label}: block length mismatch: "
                    f"received {len(block_data)}, "
                    f"expected {request_length}"
                )

            print(f"{label} requested : {request_length} bytes")
            print(f"{label} received  : {len(block_data)} bytes")

            if block_data:
                print(
                    f"{label} first 32 : "
                    f"{block_data[:32].hex(' ')}"
                )

                print(
                    f"{label} last 32  : "
                    f"{block_data[-32:].hex(' ')}"
                )

            blocks.append(block_data)

            remaining -= request_length
            block_index += 1

            print(f"Remaining       : {remaining} bytes")

        # =========================================================
        # COMBINE ALL A4 BLOCKS
        # =========================================================

        combined = b"".join(blocks)

        print("\n" + "=" * 80)
        print("A4 COMBINED DATA")
        print("=" * 80)

        print(f"Expected bytes : {total_data_length}")
        print(f"Received bytes : {len(combined)}")
        print(f"A4 blocks      : {len(blocks)}")

        if len(combined) != total_data_length:
            raise ValueError(
                f"A4 combined length mismatch: "
                f"received {len(combined)}, "
                f"expected {total_data_length}"
            )

        print("STATUS: A4 DATA SIZE OK")

        # ---------------------------------------------------------
        # The parser expects:
        #
        #   4-byte first card ID
        #   (count - 1) * 12-byte records
        #   final 8-byte record
        #
        # The final 00 00 response terminator is NOT part of the
        # attendance data. It was validated separately above.
        # ---------------------------------------------------------

        return combined, None

    def parse_attendance(self, payload, expected_count):
        """
        Parse the A4 attendance chain.

        Layout:
            00-03 : initial card ID

            For records 1 through count-1:
                00-01 : header
                02    : event
                03    : reserved
                04-07 : packed timestamp
                08-11 : next card ID

            Final record:
                00-01 : header
                02    : event
                03    : reserved
                04-07 : packed timestamp
                08-09 : final terminator bytes (00 00)

        The final record has no next card ID.
        """
        if len(payload) < 14:
            raise ValueError("A4 payload is too short to contain attendance data")

        first_card_id = int.from_bytes(payload[0:4], "little")
        offset = 4
        current_card_id = first_card_id
        records = []

        print("\n" + "=" * 80)
        print("PARSING ATTENDANCE")
        print("=" * 80)
        print(f"First card ID: {first_card_id}")

        # count - 1 normal records
        for number in range(1, expected_count):
            if offset + 12 > len(payload):
                raise ValueError(
                    f"Record {number}: not enough bytes for 12-byte record"
                )

            raw = payload[offset:offset + 12]

            event = raw[2]
            timestamp_raw = raw[4:8]
            timestamp = decode_timestamp(timestamp_raw)
            next_card_id = int.from_bytes(raw[8:12], "little")

            records.append({
                "record_number": number,
                "card_id": current_card_id,
                "event": event,
                "timestamp": timestamp,
                "timestamp_raw": timestamp_raw.hex(" "),
                "next_card_id": next_card_id,
                "raw": raw.hex(" "),
            })

            print(
                f"Record {number}: {raw.hex(' ')}"
            )

            current_card_id = next_card_id
            offset += 12

        # ---------------------------------------------------------
        # Final record
        #
        # The final attendance record contains only 8 data bytes:
        #
        #   00-01 : header
        #   02    : event
        #   03    : reserved
        #   04-07 : packed timestamp
        #
        # The device's A4 response terminator (00 00) has already
        # been removed from the payload and validated separately.
        # ---------------------------------------------------------

        if offset + 8 != len(payload):
            raise ValueError(
                f"Final record boundary mismatch: "
                f"need 8 bytes at offset {offset}, "
                f"but payload length is {len(payload)}"
            )

        final_raw = payload[offset:offset + 8]

        final_event = final_raw[2]
        final_timestamp_raw = final_raw[4:8]
        final_timestamp = decode_timestamp(final_timestamp_raw)

        records.append({
            "record_number": expected_count,
            "card_id": current_card_id,
            "event": final_event,
            "timestamp": final_timestamp,
            "timestamp_raw": final_timestamp_raw.hex(" "),
            "next_card_id": None,
            "raw": final_raw.hex(" "),
        })

        print(
            f"Final record {expected_count}: "
            f"{final_raw.hex(' ')}"
        )

        offset += 8
        print("\n" + "-" * 80)
        print("Parsing summary")
        print("-" * 80)
        print("Expected records :", expected_count)
        print("Parsed records   :", len(records))
        print("Payload bytes    :", len(payload))
        print("Consumed bytes   :", offset)
        print("Remaining bytes  :", len(payload) - offset)

        if len(records) != expected_count:
            raise ValueError(
                f"Parsed {len(records)} records, expected {expected_count}"
            )

        if offset != len(payload):
            raise ValueError(
                f"Parser left {len(payload) - offset} unconsumed bytes"
            )

        invalid_timestamps = [
            r["record_number"]
            for r in records
            if r["timestamp"] is None
        ]

        if invalid_timestamps:
            raise ValueError(
                "Invalid timestamps found in records: "
                + ", ".join(map(str, invalid_timestamps))
            )

        print("Timestamp validation: ALL VALID")

        print("STATUS           : SUCCESS")

        return records

    def print_records(self, records):
        print("\n" + "=" * 90)
        print("ATTENDANCE RECORDS")
        print("=" * 90)

        print(
            f"{'#':>4} "
            f"{'CARD ID':>10} "
            f"{'DATE':>12} "
            f"{'TIME':>8} "
            f"{'EVENT':>8} "
            f"{'NEXT ID':>10}"
        )

        print("-" * 90)

        for record in records:
            timestamp = record["timestamp"]

            if timestamp is not None:
                date_text = timestamp.strftime("%d-%m-%Y")
                time_text = timestamp.strftime("%H:%M")
            else:
                date_text = "INVALID"
                time_text = "INVALID"

            next_id = (
                "FINAL"
                if record["next_card_id"] is None
                else str(record["next_card_id"])
            )

            print(
                f"{record['record_number']:>4} "
                f"{record['card_id']:>10} "
                f"{date_text:>12} "
                f"{time_text:>8} "
                f"0x{record['event']:02X} "
                f"{next_id:>10}"
            )

        print("-" * 90)

    def run(self):
        self.connect()

        try:
            self.initialize()

            count = self.get_record_count()

            if count == 0:
                print("Device has zero attendance records.")
                return []

            payload, _ = self.get_logs_raw(count)

            records = self.parse_attendance(
                payload,
                count,
            )

            self.print_records(records)

            finish_response = self.command("finish_81")

            if len(finish_response) != 10:
                print(
                    f"WARNING: finish_81 returned {len(finish_response)} bytes"
                )

            return records

        finally:
            self.close()


if __name__ == "__main__":
    tester = SecureyeTester()

    try:
        records = tester.run()

        if not records:
            raise ValueError("No attendance records were returned")

        print("\n" + "=" * 80)
        print("TEST PASSED")
        print("=" * 80)
        print(f"Successfully parsed {len(records)} attendance records.")

    except Exception as e:
        print("\n" + "=" * 80)
        print("TEST FAILED")
        print("=" * 80)
        print(f"{type(e).__name__}: {e}")

    finally:
        tester.close()

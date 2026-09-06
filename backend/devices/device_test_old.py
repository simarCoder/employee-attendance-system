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
    """Decode Secureye packed 4-byte timestamp."""

    if len(raw) != 4:
        return None

    value = int.from_bytes(raw, "little")

    minute = (value >> 26) & 0x3F
    hour = (value >> 21) & 0x1F
    day = (value >> 16) & 0x1F
    month = (value >> 12) & 0x0F
    year = (value & 0x0FFF) + 1521

    try:
        return datetime(
            year,
            month,
            day,
            hour,
            minute
        )
    except ValueError:
        return None


class SecureyeTester:

    def __init__(
        self,
        host=DEVICE_IP,
        port=DEVICE_PORT,
        timeout=TIMEOUT
    ):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = None

    # ------------------------------------------------------------
    # CONNECTION
    # ------------------------------------------------------------

    def connect(self):

        self.sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        )

        self.sock.settimeout(self.timeout)

        self.sock.connect(
            (self.host, self.port)
        )

        print(
            f"Connected to "
            f"{self.host}:{self.port}"
        )

    def close(self):

        if self.sock:

            try:
                self.sock.close()

            except Exception:
                pass

            self.sock = None

    # ------------------------------------------------------------
    # RECEIVE
    # ------------------------------------------------------------

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

    # ------------------------------------------------------------
    # COMMAND
    # ------------------------------------------------------------

    def command(self, name):

        frame = FRAMES[name]

        print("\n" + "=" * 80)
        print(f"TX [{name}]")
        print("=" * 80)

        print(frame.hex(" "))

        self.sock.sendall(frame)

        response = self.recv_until_quiet()

        print(
            f"RX [{name}] "
            f"({len(response)} bytes)"
        )

        if response:

            print(
                response.hex(" ")
            )

        return response

    # ------------------------------------------------------------
    # INITIALIZATION
    # ------------------------------------------------------------

    def initialize(self):

        self.command("init")

        self.command("info_1")

        self.command("info_2")

        self.command("info_3")

        self.command("info_4")

        self.command("cmd_81")

    # ------------------------------------------------------------
    # B4 RECORD COUNT
    # ------------------------------------------------------------

    def get_record_count(self):

        response = self.command("cmd_b4")

        if len(response) < 6:

            raise ValueError(
                "Invalid B4 response"
            )

        # aa 55 01 01 COUNT ...
        count = int.from_bytes(
            response[4:6],
            "little"
        )

        print(
            "\nDevice reports "
            f"{count} attendance records"
        )

        return count

    # ------------------------------------------------------------
    # A4 RESPONSE EXTRACTION
    # ------------------------------------------------------------

    def extract_a4_data(self, response):

        if len(response) < 12:

            raise ValueError(
                f"A4 response too short: "
                f"{len(response)} bytes"
            )

        # Response:
        #
        # 0-9    : response header
        # 10-11  : 55 aa
        # 12...  : A4 payload
        #
        # The last 2 bytes of the payload
        # are 00 00 terminator bytes.

        if response[10:12] != b"\x55\xaa":

            raise ValueError(
                "A4 response missing "
                "55 aa payload marker"
            )

        payload = response[12:]

        if len(payload) < 2:

            raise ValueError(
                "A4 payload too short"
            )

        if payload[-2:] != b"\x00\x00":

            print(
                "WARNING: A4 payload does "
                "not end with 00 00"
            )

        data = payload[:-2]

        return data

    # ------------------------------------------------------------
    # REAL A4 DOWNLOAD
    # ------------------------------------------------------------

    def get_logs_raw(self, count):

        print("\n" + "=" * 80)
        print("A4 ATTENDANCE DOWNLOAD")
        print("=" * 80)

        # ========================================================
        # A4 #1
        #
        # 55 aa 01 a4
        # 00 00 00 00
        # COUNT
        # 00 00
        # 00 04
        # 08 00
        #
        # For 105:
        # 69 00
        #
        # For 106:
        # 6a 00
        # ========================================================

        first_request = (
            bytes.fromhex(
                "55 aa 01 a4 "
                "00 00 00 00"
            )
            + count.to_bytes(
                2,
                "little"
            )
            + bytes.fromhex(
                "00 00 00 04 08 00"
            )
        )

        print("\n" + "-" * 80)
        print("A4 #1")
        print("-" * 80)

        print(
            "TX:",
            first_request.hex(" ")
        )

        self.sock.sendall(
            first_request
        )

        first_response = (
            self.recv_until_quiet()
        )

        print(
            "RX length:",
            len(first_response)
        )

        if not first_response:

            raise ValueError(
                "A4 #1 returned no data"
            )

        first_data = (
            self.extract_a4_data(
                first_response
            )
        )

        print(
            "A4 #1 data:",
            len(first_data),
            "bytes"
        )

        print(
            "First 32:",
            first_data[:32].hex(" ")
        )

        print(
            "Last 32:",
            first_data[-32:].hex(" ")
        )

        # ========================================================
        # Calculate remaining bytes
        #
        # Attendance records are 12 bytes each.
        #
        # First A4 transfers 1024 data bytes.
        #
        # remaining = count * 12 - 1024
        # ========================================================

        total_data_bytes = count * 12

        first_block_size = len(first_data)

        remaining = (
            total_data_bytes
            - first_block_size
        )

        if remaining < 0:

            raise ValueError(
                f"Invalid remaining size: "
                f"{remaining}"
            )

        print(
            "\nTotal expected attendance data:",
            total_data_bytes,
            "bytes"
        )

        print(
            "First A4 data:",
            first_block_size,
            "bytes"
        )

        print(
            "Remaining:",
            remaining,
            "bytes"
        )

        # ========================================================
        # A4 #2
        #
        # For 105:
        #
        # ... 01 00 EC 00 09 00
        #
        # For 106:
        #
        # ... 01 00 F8 00 09 00
        #
        # ========================================================

        if remaining > 0:

            second_request = (
                bytes.fromhex(
                    "55 aa 01 a4 "
                    "00 00 00 00 "
                    "00 00 01 00"
                )
                + remaining.to_bytes(
                    2,
                    "little"
                )
                + bytes.fromhex(
                    "09 00"
                )
            )

            print("\n" + "-" * 80)
            print("A4 #2")
            print("-" * 80)

            print(
                "TX:",
                second_request.hex(" ")
            )

            self.sock.sendall(
                second_request
            )

            second_response = (
                self.recv_until_quiet()
            )

            print(
                "RX length:",
                len(second_response)
            )

            if not second_response:

                raise ValueError(
                    "A4 #2 returned no data"
                )

            second_data = (
                self.extract_a4_data(
                    second_response
                )
            )

            print(
                "A4 #2 data:",
                len(second_data),
                "bytes"
            )

            print(
                "First 32:",
                second_data[:32].hex(" ")
            )

            print(
                "Last 32:",
                second_data[-32:].hex(" ")
            )

        else:

            second_response = b""
            second_data = b""

            print(
                "\nNo second A4 request needed."
            )

        # ========================================================
        # COMBINE
        # ========================================================

        combined = (
            first_data +
            second_data
        )

        print("\n" + "=" * 80)
        print("A4 COMBINED DATA")
        print("=" * 80)

        print(
            "Expected:",
            total_data_bytes,
            "bytes"
        )

        print(
            "Received:",
            len(combined),
            "bytes"
        )

        if len(combined) != total_data_bytes:

            raise ValueError(
                "A4 data size mismatch: "
                f"expected {total_data_bytes}, "
                f"got {len(combined)}"
            )

        print(
            "STATUS: A4 DATA SIZE OK"
        )

        return combined

    # ------------------------------------------------------------
    # PARSE ATTENDANCE
    # ------------------------------------------------------------

    def parse_attendance(self, payload, expected_count):

        print("\n" + "=" * 80)
        print("PARSING ATTENDANCE")
        print("=" * 80)

        if len(payload) < 4:
            raise ValueError("A4 payload too short")

        # First 4 bytes are the first card ID
        first_card_id = int.from_bytes(
            payload[0:4],
            "little"
        )

        print(
            "First card ID:",
            first_card_id
        )

        records = []

        current_card_id = first_card_id

        offset = 4

        for number in range(1, expected_count + 1):

            remaining = len(payload) - offset

            # Last record is special.
            # We need at least 8 bytes here for the
            # 106-record capture because the record
            # crosses the A4 response boundary.
            if number < expected_count:

                if remaining < 12:
                    raise ValueError(
                        f"Record {number}: "
                        f"only {remaining} bytes remain"
                    )

                raw = payload[
                    offset:
                    offset + 12
                ]

                event = raw[2]

                timestamp_raw = raw[4:8]

                timestamp = decode_timestamp(
                    timestamp_raw
                )

                next_card_id = int.from_bytes(
                    raw[8:12],
                    "little"
                )

                print(
                    f"Record {number}: "
                    f"{raw.hex(' ')}"
                )

                records.append({
                    "record_number": number,
                    "card_id": current_card_id,
                    "event": event,
                    "timestamp": timestamp,
                    "timestamp_raw": timestamp_raw.hex(" "),
                    "next_card_id": next_card_id,
                    "raw": raw.hex(" "),
                })

                current_card_id = next_card_id

                offset += 12

            else:

                raw = payload[offset:]

                print(
                    f"Final record {number}: "
                    f"{raw.hex(' ')}"
                )

                if len(raw) < 8:
                    raise ValueError(
                        f"Final record has only "
                        f"{len(raw)} bytes"
                    )

                event = raw[2]

                timestamp_raw = raw[4:8]

                timestamp = decode_timestamp(
                    timestamp_raw
                )

                records.append({
                    "record_number": number,
                    "card_id": current_card_id,
                    "event": event,
                    "timestamp": timestamp,
                    "timestamp_raw": timestamp_raw.hex(" "),
                    "next_card_id": None,
                    "raw": raw.hex(" "),
                })

                offset += len(raw)

        print("\nParsing summary")
        print("----------------")
        print(
            "Expected records :",
            expected_count
        )
        print(
            "Parsed records   :",
            len(records)
        )
        print(
            "Payload bytes    :",
            len(payload)
        )
        print(
            "Consumed bytes   :",
            offset
        )
        print(
            "Remaining bytes  :",
            len(payload) - offset
        )

        return records

    # ------------------------------------------------------------
    # PRINT RECORDS
    # ------------------------------------------------------------

    def print_records(self, records):

        print("\n" + "=" * 100)
        print("ATTENDANCE RECORDS")
        print("=" * 100)

        print(
            f"{'#':>4} "
            f"{'DATE':>12} "
            f"{'TIME':>8} "
            f"{'EVENT':>8} "
            f"{'NEXT ID':>12}"
        )

        print("-" * 100)

        for record in records:

            timestamp = record[
                "timestamp"
            ]

            if timestamp:

                date_text = timestamp.strftime(
                    "%d-%m-%Y"
                )

                time_text = timestamp.strftime(
                    "%H:%M"
                )

            else:

                date_text = "INVALID"
                time_text = "INVALID"

            print(
                f"{record['record_number']:>4} "
                f"{date_text:>12} "
                f"{time_text:>8} "
                f"0x{record['event']:02X} "
                f"{record['next_card_id']:>12}"
            )

        print("-" * 100)

    # ------------------------------------------------------------
    # RUN
    # ------------------------------------------------------------

    def run(self):

        self.connect()

        try:

            self.initialize()

            count = (
                self.get_record_count()
            )

            if count == 0:

                print(
                    "Device has zero "
                    "attendance records."
                )

                return []

            payload = (
                self.get_logs_raw(
                    count
                )
            )

            records = (
                self.parse_attendance(
                    payload,
                    count
                )
            )

            self.print_records(
                records
            )

            print("\n" + "=" * 80)
            print("TEST COMPLETE")
            print("=" * 80)

            self.command(
                "finish_81"
            )

            return records

        finally:

            self.close()


if __name__ == "__main__":

    tester = SecureyeTester()

    try:

        tester.run()

    except Exception as e:

        print(
            "\nTEST FAILED:",
            type(e).__name__,
            ":",
            e
        )

    finally:

        tester.close()
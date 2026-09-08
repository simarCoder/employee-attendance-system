import socket
from datetime import datetime
from backend.services.settings import get_secureye_config


def create_configured_secureye():
    config = get_secureye_config()

    if not config["ip"]:
        raise RuntimeError(
            "Secureye IP address is not configured."
        )

    return Secureye(
        host=config["ip"],
        port=config["port"],
        timeout=config["timeout"]
    )

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


# def decode_timestamp(raw):
#     value = int.from_bytes(raw, "little")

#     minute = (value >> 26) & 0x3F
#     hour = (value >> 21) & 0x1F
#     day = (value >> 16) & 0x1F
#     month = (value >> 12) & 0x0F
#     year_field = value & 0x0FFF

#     year = year_field + 1521

#     return datetime(
#         year,
#         month,
#         day,
#         hour,
#         minute
#     )


def decode_timestamp(raw):
    """
    Decode the Secureye packed 4-byte timestamp.

    Secureye timestamp format:

        bits 26-31 : minute
        bits 21-25 : hour
        bits 16-20 : day
        bits 12-15 : month
        bits  0-11 : year - 1521
    """

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


class Secureye:

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

    def connect(self):
        self.sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        )

        self.sock.settimeout(self.timeout)

        self.sock.connect(
            (self.host, self.port)
        )

    def send(self, data):
        self.sock.sendall(data)

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

        self.send(FRAMES[name])

        return self.recv_until_quiet()

    def get_record_count(self):
        response = self.command("cmd_b4")

        if len(response) < 6:
            raise ValueError("Invalid B4 response")

        count = int.from_bytes(
            response[4:6],
            "little"
        )

        return count
    @staticmethod
    def make_a4_first_request(count):
        return (
            bytes.fromhex(
                "55 aa 01 a4 00 00 00 00"
            )
            + count.to_bytes(4, "little")
            + bytes.fromhex("00 04 08 00")
        )
        
        
        
    # def get_logs(self, count):

    #     if count <= 0:
    #         return []

    #     data_length = count * 12

    #     request = (
    #         bytes.fromhex(
    #             "55 aa 01 a4 00 00 00 00"
    #         )
    #         + count.to_bytes(4, "little")
    #         + data_length.to_bytes(2, "little")
    #         + bytes.fromhex("08 00")
    #     )

    #     self.send(request)

    #     response = self.recv_until_quiet(5.0)

    #     if len(response) < 16:
    #         raise ValueError("Invalid A4 response")

    #     # 10-byte ACK + 6-byte A4 header
    #     header = response[10:16]

    #     payload = response[16:]

    #     # -------------------------------------------------
    #     # CRITICAL DISCOVERY
    #     #
    #     # First card ID lives in A4 header byte 2
    #     # Example:
    #     #
    #     # 55 aa 01 00 00 00
    #     #       ^^
    #     #       first card ID
    #     # -------------------------------------------------

    #     first_card_id = header[2]

    #     records = []

    #     offset = 0
    #     current_card_id = first_card_id

    #     while offset < len(payload):

    #         remaining = len(payload) - offset

    #         # Complete record
    #         if remaining >= 12:

    #             raw = payload[
    #                 offset:
    #                 offset + 12
    #             ]

    #             event = raw[2]

    #             timestamp_raw = raw[4:8]

    #             next_card_id = int.from_bytes(
    #                 raw[8:12],
    #                 "little"
    #             )

    #             timestamp = decode_timestamp(
    #                 timestamp_raw
    #             )

    #             records.append({
    #                 "card_id": current_card_id,
    #                 "event": event,
    #                 "timestamp": timestamp,
    #                 "timestamp_raw": timestamp_raw.hex(" "),
    #                 "next_card_id": next_card_id,
    #                 "raw": raw.hex(" "),
    #             })

    #             current_card_id = next_card_id

    #             offset += 12

    #         else:

    #             # Final 10-byte record
    #             if remaining >= 8:

    #                 raw = payload[offset:]

    #                 event = raw[2]

    #                 timestamp_raw = raw[4:8]

    #                 timestamp = decode_timestamp(
    #                     timestamp_raw
    #                 )

    #                 records.append({
    #                     "card_id": current_card_id,
    #                     "event": event,
    #                     "timestamp": timestamp,
    #                     "timestamp_raw": timestamp_raw.hex(" "),
    #                     "next_card_id": None,
    #                     "raw": raw.hex(" "),
    #                 })

    #             break

    #     return records
    @staticmethod
    def make_a4_continuation_request(
        block_index,
        request_length
    ):
        if block_index < 1:
            raise ValueError(
                "Continuation block_index must be >= 1"
            )

        if request_length <= 0:
            raise ValueError(
                "request_length must be > 0"
            )

        if request_length > 0xFFFF:
            raise ValueError(
                "request_length is too large"
            )

        stage = 8 + block_index

        return (
            bytes.fromhex(
                "55 aa 01 a4 00 00 00 00"
            )
            + b"\x00\x00"
            + block_index.to_bytes(2, "little")
            + request_length.to_bytes(2, "little")
            + stage.to_bytes(2, "little")
        )
        
    def send_a4(self, request):
        self.send(request)

        response = self.recv_until_quiet(5.0)

        if len(response) < 14:
            raise ValueError(
                f"Invalid A4 response: {len(response)} bytes"
            )

        if response[10:12] != b"\x55\xaa":
            raise ValueError(
                "Invalid A4 response: missing 55 aa payload marker"
            )

        return response
    def get_logs_raw(self, count):

        if count <= 0:
            return b""

        total_data_length = count * 12

        blocks = []
        remaining = total_data_length
        block_index = 0

        while remaining > 0:

            if block_index == 0:

                request_length = min(
                    1024,
                    remaining
                )

                request = self.make_a4_first_request(
                    count
                )

            else:

                request_length = min(
                    1024,
                    remaining
                )

                request = self.make_a4_continuation_request(
                    block_index,
                    request_length
                )

            response = self.send_a4(request)

            raw_data = response[12:]

            expected_response_data = (
                request_length + 2
            )

            if len(raw_data) != expected_response_data:
                raise ValueError(
                    "A4 response size mismatch: "
                    f"received {len(raw_data)}, "
                    f"expected {expected_response_data}"
                )

            if raw_data[-2:] != b"\x00\x00":
                raise ValueError(
                    "A4 response missing 00 00 terminator"
                )

            block_data = raw_data[:-2]

            if len(block_data) != request_length:
                raise ValueError(
                    "A4 block length mismatch: "
                    f"received {len(block_data)}, "
                    f"expected {request_length}"
                )

            blocks.append(block_data)

            remaining -= request_length
            block_index += 1

        combined = b"".join(blocks)

        if len(combined) != total_data_length:
            raise ValueError(
                "A4 combined data length mismatch: "
                f"received {len(combined)}, "
                f"expected {total_data_length}"
            )

        return combined
    
    def parse_attendance(self, payload, expected_count):

        if len(payload) != expected_count * 12:
            raise ValueError(
                "A4 payload length mismatch: "
                f"received {len(payload)}, "
                f"expected {expected_count * 12}"
            )

        if len(payload) < 14:
            raise ValueError(
                "A4 payload is too short"
            )

        first_card_id = int.from_bytes(
            payload[0:4],
            "little"
        )

        offset = 4
        current_card_id = first_card_id
        records = []

        for number in range(
            1,
            expected_count
        ):

            if number < expected_count:

                if offset + 12 > len(payload):
                    raise ValueError(
                        f"Record {number}: "
                        "not enough bytes"
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

                if timestamp is None:
                    raise ValueError(
                        f"Invalid timestamp in record {number}: "
                        f"{timestamp_raw.hex(' ')}"
                    )

                next_card_id = int.from_bytes(
                    raw[8:12],
                    "little"
                )

                records.append({
                    "record_number": number,
                    "card_id": current_card_id,
                    "event": event,
                    "timestamp": timestamp,
                    "timestamp_raw":
                        timestamp_raw.hex(" "),
                    "next_card_id": next_card_id,
                    "raw": raw.hex(" "),
                })

                current_card_id = next_card_id

                offset += 12

        final_raw = payload[offset:]

        if len(final_raw) != 8:
            raise ValueError(
                "Invalid final attendance record: "
                f"{len(final_raw)} bytes"
            )

        final_event = final_raw[2]

        final_timestamp_raw = final_raw[4:8]

        final_timestamp = decode_timestamp(
            final_timestamp_raw
        )

        if final_timestamp is None:
            raise ValueError(
                "Invalid final attendance timestamp: "
                f"{final_timestamp_raw.hex(' ')}"
            )

        records.append({
            "record_number": expected_count,
            "card_id": current_card_id,
            "event": final_event,
            "timestamp": final_timestamp,
            "timestamp_raw":
                final_timestamp_raw.hex(" "),
            "next_card_id": None,
            "raw": final_raw.hex(" "),
        })

        if len(records) != expected_count:
            raise ValueError(
                f"Parsed {len(records)} records, "
                f"expected {expected_count}"
            )

        return records
    def download_records(self):

        self.connect()

        try:

            self.command("init")
            self.command("info_1")
            self.command("info_2")
            self.command("info_3")
            self.command("info_4")
            self.command("cmd_81")

            count = self.get_record_count()

            if count == 0:
                self.command("finish_81")
                return []

            payload = self.get_logs_raw(count)

            records = self.parse_attendance(
                payload,
                count
            )

            self.command("finish_81")

            return records

        finally:
            self.close()

    def close(self):

        if self.sock:

            try:
                self.sock.close()

            finally:
                self.sock = None
                
                
def test_secureye_connection():
    config = get_secureye_config()

    if not config["ip"]:
        raise RuntimeError(
            "Secureye IP address is not configured."
        )

    device = Secureye(
        host=config["ip"],
        port=config["port"],
        timeout=config["timeout"]
    )

    device.connect()

    try:
        responses = {}

        # Same initialization sequence used by real attendance download
        responses["init"] = device.command("init")
        responses["info_1"] = device.command("info_1")
        responses["info_2"] = device.command("info_2")
        responses["info_3"] = device.command("info_3")
        responses["info_4"] = device.command("info_4")
        responses["cmd_81"] = device.command("cmd_81")

        # Read actual record count from the machine
        record_count = device.get_record_count()

        # Finish the protocol session cleanly
        responses["finish_81"] = device.command("finish_81")

        return {
            "success": True,
            "ip": config["ip"],
            "port": config["port"],
            "timeout": config["timeout"],
            "record_count": record_count,
            "responses": {
                key: value.hex(" ")
                for key, value in responses.items()
            }
        }

    finally:
        device.close()
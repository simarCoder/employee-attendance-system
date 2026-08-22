import socket


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
        "55 aa 01 81 01 00 00 00 00 00 ff ff 00 00 09 00"
    ),
}


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

    # ---------------------------------------------------------
    # CONNECTION
    # ---------------------------------------------------------

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
            f"CONNECTED: {self.host}:{self.port}"
        )

    # ---------------------------------------------------------
    # SEND
    # ---------------------------------------------------------

    def send(self, data, name="raw"):

        print(
            f"\nTX [{name}] ({len(data)} bytes)"
        )

        print(
            data.hex(" ")
        )

        self.sock.sendall(data)

    # ---------------------------------------------------------
    # RECEIVE EXACT
    # ---------------------------------------------------------

    def recv_exact(self, size):

        data = bytearray()

        while len(data) < size:

            chunk = self.sock.recv(
                size - len(data)
            )

            if not chunk:

                raise ConnectionError(
                    f"Connection closed at "
                    f"{len(data)}/{size} bytes"
                )

            data.extend(chunk)

        return bytes(data)

    # ---------------------------------------------------------
    # RECEIVE UNTIL SHORT SILENCE
    # ---------------------------------------------------------

    def recv_until_quiet(self, quiet=0.5):

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

    # ---------------------------------------------------------
    # NORMAL COMMAND
    # ---------------------------------------------------------

    def command(self, name):

        self.send(
            FRAMES[name],
            name
        )

        response = self.recv_until_quiet()

        print(
            f"RX [{len(response)} bytes]"
        )

        print(
            response.hex(" ")
        )

        return response

    # ---------------------------------------------------------
    # B4
    # ---------------------------------------------------------

    def get_record_count(self):

        response = self.command("cmd_b4")

        if len(response) < 10:

            raise ValueError(
                "B4 response is shorter than 10 bytes"
            )

        print("\n=== B4 ANALYSIS ===")

        print(
            "Response:",
            response.hex(" ")
        )

        # Your capture:
        #
        # aa 55 01 01 0d 00 00 00 00 00
        #
        # Therefore byte 4 = 0d

        count = response[4]

        print(
            f"B4 value = {count} "
            f"(0x{count:02X})"
        )

        return count

    # ---------------------------------------------------------
    # A4
    # ---------------------------------------------------------

    def get_logs(self, count):

        if count <= 0:

            print(
                "\nDEVICE REPORTS ZERO RECORDS"
            )

            return b""

        data_length = count * 12

        # Based directly on your ONtime captures:
        #
        # 55 aa 01 a4
        # 00 00 00 00
        # count
        # data_length
        # 08 00

        request = (
            bytes.fromhex(
                "55 aa 01 a4 00 00 00 00"
            )
            + count.to_bytes(
                4,
                "little"
            )
            + data_length.to_bytes(
                2,
                "little"
            )
            + bytes.fromhex(
                "08 00"
            )
        )

        print("\n=== A4 REQUEST ===")

        print(
            f"Record count : {count}"
        )

        print(
            f"Data length  : {data_length}"
        )

        self.send(
            request,
            "get_logs"
        )

        response = self.recv_until_quiet(
                quiet=5.0
                )

        print(
            f"\nRX A4 [{len(response)} bytes]"
        )

        print(
            response.hex(" ")
        )

        expected = 10 + 6 + data_length

        print("\n=== A4 LENGTH CHECK ===")

        print(
            f"Expected : {expected}"
        )

        print(
            f"Received : {len(response)}"
        )

        if len(response) != expected:

            print(
                "WARNING: response length differs "
                "from advertised length."
            )

        return response

    # ---------------------------------------------------------
    # FINISH
    # ---------------------------------------------------------

    def finish(self):

        response = self.command(
            "finish_81"
        )

        return response

    # ---------------------------------------------------------
    # CLOSE
    # ---------------------------------------------------------

    def close(self):

        if self.sock:

            self.sock.close()
            self.sock = None
            
            
            
def decode_timestamp(raw):

    value = int.from_bytes(
        raw,
        "little"
    )

    minute = (value >> 26) & 0x3F
    hour = (value >> 21) & 0x1F
    day = (value >> 16) & 0x1F
    month = (value >> 12) & 0x0F
    year_field = value & 0x0FFF

    year = year_field + 1521

    return (
        f"{day:02d}-"
        f"{month:02d}-"
        f"{year:04d} "
        f"{hour:02d}:"
        f"{minute:02d}"
    )
    
    
def parse_attendance_response(response):

    ACK_SIZE = 10
    HEADER_SIZE = 6
    RECORD_SIZE = 12

    if len(response) < ACK_SIZE + HEADER_SIZE:
        raise ValueError("A4 response too short")

    # ---------------------------------------------------------
    # A4 HEADER
    # ---------------------------------------------------------

    header = response[
        ACK_SIZE:
        ACK_SIZE + HEADER_SIZE
    ]

    if header[0:2] != bytes.fromhex("55 aa"):
        raise ValueError(
            f"Invalid A4 header: {header.hex(' ')}"
        )

    # ---------------------------------------------------------
    # IMPORTANT DISCOVERY:
    #
    # 55 aa XX 00 00 00
    #       ^^
    #       First record's Card ID
    # ---------------------------------------------------------

    first_card_id = header[2]

    payload = response[
        ACK_SIZE + HEADER_SIZE:
    ]

    print("\n=== A4 HEADER ===")
    print(header.hex(" "))

    print(
        f"FIRST CARD ID: {first_card_id}"
    )

    print(
        f"A4 payload bytes: {len(payload)}"
    )

    # ---------------------------------------------------------
    # RAW PAYLOAD
    # ---------------------------------------------------------

    print("\n=== RAW PAYLOAD ===")

    for i, b in enumerate(payload):
        print(
            f"{i:02d}: {b:02X}"
        )

    records = []

    offset = 0

    # ---------------------------------------------------------
    # COMPLETE 12-BYTE RECORDS
    # ---------------------------------------------------------

    while offset + RECORD_SIZE <= len(payload):

        raw = payload[
            offset:
            offset + RECORD_SIZE
        ]

        event = raw[2]

        timestamp_raw = raw[4:8]

        next_card_id = int.from_bytes(
            raw[8:12],
            "little"
        )

        print("\n================================")
        print(
            f"12-BYTE RECORD "
            f"{len(records) + 1}"
        )
        print("================================")

        print(
            "RAW:",
            raw.hex(" ")
        )

        print(
            f"EVENT      : 0x{event:02X}"
        )

        print(
            f"TIMESTAMP  : "
            f"{timestamp_raw.hex(' ')}"
        )

        print(
            f"NEXT ID    : "
            f"{raw[8:12].hex(' ')}"
        )

        print(
            f"NEXT ID VALUE: "
            f"{next_card_id}"
        )

        records.append({
            "index": len(records) + 1,

            "event": event,

            "timestamp": decode_timestamp(
                timestamp_raw
            ),

            "timestamp_raw":
                timestamp_raw.hex(" "),

            # This belongs to the NEXT record.
            "next_card_id": next_card_id,

            # Filled below.
            "card_id": None,

            "raw": raw,

            "complete": True,
        })

        offset += RECORD_SIZE

    # ---------------------------------------------------------
    # FINAL PARTIAL RECORD
    #
    # Usually the final record is only 10 bytes because
    # there is no following record/card ID field.
    # ---------------------------------------------------------

    remainder = payload[offset:]

    if remainder:

        print("\n================================")
        print("FINAL PARTIAL RECORD")
        print("================================")

        print(
            f"Bytes received: "
            f"{len(remainder)}"
        )

        print(
            remainder.hex(" ")
        )

        if len(remainder) >= 8:

            event = remainder[2]

            timestamp_raw = remainder[4:8]

            records.append({
                "index": len(records) + 1,

                "event": event,

                "timestamp":
                    decode_timestamp(
                        timestamp_raw
                    ),

                "timestamp_raw":
                    timestamp_raw.hex(" "),

                # No next ID exists in the
                # final partial record.
                "next_card_id": None,

                "card_id": None,

                "raw": remainder,

                "complete": False,
            })

    # ---------------------------------------------------------
    # CARD ID ASSIGNMENT
    #
    # NEW MODEL:
    #
    # Record 1 Card ID = A4 header byte 2
    #
    # Record N Card ID =
    # previous record's next_card_id
    # ---------------------------------------------------------

    print("\n================================")
    print("CARD ID RECONSTRUCTION")
    print("================================")

    if records:

        # FIRST RECORD
        records[0]["card_id"] = first_card_id

        print(
            f"Record 1 Card ID "
            f"<- A4 header = "
            f"{first_card_id}"
        )

        # REMAINING RECORDS
        for i in range(1, len(records)):

            previous = records[i - 1]

            current = records[i]

            candidate_card = (
                previous["next_card_id"]
            )

            current["card_id"] = candidate_card

            print(
                f"Record {current['index']} "
                f"Card ID <- "
                f"Record {previous['index']} "
                f"NEXT ID = "
                f"{candidate_card}"
            )

    return records

def main():

    device = Secureye()

    try:

        device.connect()

        print(
            "\n================================"
        )

        print(
            "SECUREYE ONTIME PUNCH DOWNLOAD"
        )

        print(
            "================================"
        )

        # -------------------------------------------------
        # SESSION
        # -------------------------------------------------

        device.command("init")

        device.command("info_1")

        device.command("info_2")

        device.command("info_3")

        device.command("info_4")

        device.command("cmd_81")

        # -------------------------------------------------
        # ASK DEVICE HOW MANY RECORDS
        # -------------------------------------------------

        count = device.get_record_count()

        print(
            f"\nDEVICE SAYS: {count} RECORDS"
        )

        # -------------------------------------------------
        # FETCH ALL REPORTED RECORDS
        # -------------------------------------------------

        a4_response = device.get_logs(
            count
        )

        # -------------------------------------------------
        # PARSE
        # -------------------------------------------------

        records = parse_attendance_response(a4_response)
        print("\n========== RAW RECORD ANALYSIS ==========")

        for i, record in enumerate(records):

            print(
                f"\nRECORD {i + 1}"
            )

            raw = record["raw"]

            print(
                "RAW :",
                raw.hex(" ")
            )

            if len(raw) >= 1:
                print(
                    "BYTE 0:",
                    hex(raw[0])
                )

            if len(raw) >= 2:
                print(
                    "BYTE 1:",
                    hex(raw[1])
                )

            if len(raw) >= 3:
                print(
                    "EVENT:",
                    hex(raw[2])
                )

            if len(raw) >= 4:
                print(
                    "BYTE 3:",
                    hex(raw[3])
                )

            if len(raw) >= 8:
                print(
                    "TIME:",
                    raw[4:8].hex(" ")
                )

            if len(raw) >= 12:

                print(
                    "NEXT CARD ID:",
                    raw[8:12].hex(" "),
                    "=",
                    record["next_card_id"]
                )

            else:

                print(
                    "NEXT CARD ID: "
                    "not present "
                    "(final partial record)"
                )

            print(
                "CARD ID:",
                record["card_id"]
            )

        print(
            "\n================================"
        )

        print(
            f"DECODED RECORDS: {len(records)}"
        )

        print(
            "================================"
        )

        for record in records:

            print(
                f"{record['index']:03d} | "
                f"ID/Card: {record['card_id']} | "
                f"{record['timestamp']} | "
                f"Event: "
                f"0x{record['event']:02X}"
            )

        # -------------------------------------------------
        # FINISH
        # -------------------------------------------------

        device.finish()

        print(
            "\nDOWNLOAD COMPLETE."
        )

    except Exception as exc:

        print(
            "\nERROR:"
        )

        print(
            type(exc).__name__,
            exc
        )

    finally:

        device.close()

        print(
            "\nConnection closed."
        )


if __name__ == "__main__":
    main()
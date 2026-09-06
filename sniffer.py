from scapy.all import sniff, IP, TCP, Raw

def packet(pkt):
    if IP in pkt and TCP in pkt:
        if pkt[IP].src == "192.168.1.224" or pkt[IP].dst == "192.168.1.224":
            print("\n", pkt[IP].src, "->", pkt[IP].dst)
            print("TCP:", pkt[TCP].sport, "->", pkt[TCP].dport)

            if Raw in pkt:
                print("DATA:", bytes(pkt[Raw]).hex(" "))

sniff(
    filter="host 192.168.1.224 and tcp port 5005",
    prn=packet,
    store=False
)
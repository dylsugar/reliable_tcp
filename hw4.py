"""
Where solution code to HW5 should be written.  No other files should
be modified.
"""

import select
import socket
import io
import time
import struct
import homework4
import homework4.logging


def get_timeout(SampleRTT, EstRTT, DevRTT):
    """
    Returns the timeout interval to determine packet 
    retransmission.
    Let SampleRTT be the amount of time between when
    packet is sent and when its ACK is received.
    SampleRTT is only computed for the packets that are
    sent once (without retransmission). So if a packet is 
    being retransmitted, we don't compute SampleRTT.
    Since SampleRTT will fluctuate, we need EstRTT, which is 
    a sort of average of the SampleRTT values.
    Initially, EstRTT = 0.
    EstRTT = (0.875 * EstRTT) + (0.125 * SampleRTT)
    In addition, we need the deviation of EstRTT.
    Let DevRTT be an estimate of how much SampleRTT typically 
    deviates from EstRTT.
    Initially, DevRTT = 0
    DevRTT = (0.75 * DevRTT) + (0.25 * abs(SampleRTT - EstRTT))
    What we need to get is the timeout interval:
    #### TimeoutInterval = EstRTT + (4 * DevRTT) ####
    Function should return tuple of (EstRTT, DevRTT, TimeoutInterval)
    """
    EstRTT = (0.875 * EstRTT) + (0.125 * SampleRTT)
    DevRTT = (0.75 * DevRTT) + (0.25 * abs(SampleRTT - EstRTT))
    TimeoutInterval = EstRTT + (4 * DevRTT)

    return (EstRTT, DevRTT, TimeoutInterval)


def extract_header(packet):
    """
    Given a received packet, extract the header bits and
    return as a tuple of (seqNum, checksum)
    """
    # Unpack the bytes in big-endian
    header = struct.unpack('>BH', packet[:3])

    return header


def extract_data(packet):
    """
    Given a received packet, extract the data
    and return as bytestring
    """
    data = packet[3:]

    return data


def carry_around_add(a, b):
    """
    Perform carry around addition for the
    1's complement sum
    """
    c = a + b
    return (c & 0xffff) + (c >> 16)


def calc_checksum(data):
    """
    Given the data to send to socket, compute and return
    the appropriate checksum bits for reliable transmission.
    """
    padding = struct.pack('B', 0)

    if len(data) % 2 != 0:
        # Number of bytes in packet is odd, must add pad byte
        data += padding

    s = 0
    for i in range(0, len(data), 2):
        w = data[i] + (data[i + 1] << 8)
        s = s + w
        s = (s & 0xffff) + (s >> 16)

    return ~s & 0xffff


def is_corrupt(packet):
    """
    Given a received packet, check if the 
    data is corrupt (using the checksum bits).
    """
    check = calc_checksum(packet)

    if check == 0x0000:
        return False
    else:
        return True


def isACK(packet, seqNum):
    """
    Given a received packet and a sequence number,
    return whether the rcvpkt is an ACK for the given
    desired seqNum or not.
    """
    num = struct.pack('B', seqNum)

    if num == packet:
        return True
    else:
        return False


def make_ACK(seqNum):
    """
    Given the seqNum, create an ACK packet
    for the receiver to send.
    """
    sndpkt = struct.pack('B', seqNum)

    return sndpkt


def make_pkt(seqNum, data):
    """
    Given the seqNum and data, create a packet for 
    the sender to send.
    """
    num = struct.pack('B', seqNum)

    checksum = calc_checksum(num + data)

    # Pack the bytes in big-endian
    header = struct.pack('>BH', seqNum, checksum)

    sndpkt = header + data

    return sndpkt


def send(sock: socket.socket, data: bytes):
    """
    Implementation of the sending logic for sending data over a slow,
    lossy, constrained network.
    Args:
        sock -- A socket object, constructed and initialized to communicate
                over a simulated lossy network.
        data -- A bytes object, containing the data to send over the network.
    """
    logger = homework4.logging.get_logger("hw5-sender")

    # Initialize the needed RTTs
    timeout = 1
    SampleRTT = 0.5
    EstRTT = 0
    DevRTT = 0

    call = 0

    # Now let's get chunkin'!
    chunk_size = homework4.MAX_PACKET
    offsets = range(0, len(data), homework4.MAX_PACKET)

    for chunk in [data[i:i + chunk_size] for i in offsets]:
        sndpkt = make_pkt(call, chunk)

        retransmit = False

        while True:
            sendTime = time.time()
            sock.send(sndpkt)

            ready = select.select([sock], [], [], timeout)

            # Check for timeout
            if ready[0]:
                rcvpkt = sock.recv(2)
                recvTime = round(time.time() - sendTime, 5)
            else:
                # TIMED OUT - RESET AND RESEND
                retransmit = True
                continue

            # Verify received ACK packet
            if isACK(rcvpkt, call):
                # Correct ACK!
                if not retransmit:
                    SampleRTT = recvTime

                EstRTT, DevRTT, timeout = get_timeout(
                    SampleRTT, EstRTT, DevRTT)

                call = 1 - call
                break

            # Otherwise, wrong ACK - RESET AND RESEND
            retransmit = True


def recv(sock: socket.socket, dest: io.BufferedIOBase) -> int:
    """
    Implementation of the receiving logic for receiving data over a slow,
    lossy, constrained network.
    Args:
        sock -- A socket object, constructed and initialized to communicate
                over a simulated lossy network.
    Return:
        The number of bytes written to the destination.
    """
    logger = homework4.logging.get_logger("hw4-receiver")

    call = 0
    num_bytes = 0

    while True:
        rcvpkt = sock.recv(homework4.MAX_PACKET + 3)
        if not rcvpkt:
            break

        seqNum, checksum = extract_header(rcvpkt)
        corrupt = is_corrupt(rcvpkt)

        # Verify received data packet
        if not corrupt and seqNum == call:
            # Valid packet, send correct ACK
            sndpkt = make_ACK(seqNum)
            sock.send(sndpkt)

            data = extract_data(rcvpkt)
            dest.write(data)
            num_bytes += len(data)
            dest.flush()

            call = 1 - call
        elif corrupt or seqNum != call:
            # Invalid packet, must send wrong ACK
            sndpkt = make_ACK(seqNum)
            sock.send(sndpkt)

    return num_bytes

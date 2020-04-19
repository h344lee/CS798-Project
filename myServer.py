import optparse
import datetime
import socket
from threading import Thread


parser = optparse.OptionParser()
parser.add_option('-i', dest='ip', default='')
parser.add_option('-p', dest='port', type='int', default=12345)
(options, args) = parser.parse_args()

# echo_handler function set a TCP server which receive msg from its clients
def echo_handler(conn, addr, terminator="10"):
    BUF_SIZE = 2048

    data = conn.recv(BUF_SIZE)
    msg = data.decode()
    print('RECEIVED: {} << {}'.format(msg, addr))
    f.write("Receiver: %s, MSG: %s, Addr: %s, Time: %s\n" % (options.ip ,msg, addr, datetime.datetime.now()))
    f.flush()
    if msg == terminator:
        conn.close()


# run_server function bind TCP socket and make a new thread to deal with the binded connection
def run_server(host=options.ip, port=options.port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        s.bind((host, port))

        while 1:
            s.listen(20)
            conn, addr = s.accept()

            t = Thread(target=echo_handler, args=(conn, addr))
            t.start()

        s.close()

    finally:
        s.close()

if __name__ == '__main__':
  f = open('raw_traffic_log.txt', 'a')
  run_server()

import socket, optparse

parser = optparse.OptionParser()
parser.add_option('-i', dest='ip', default='127.0.0.1')
parser.add_option('-p', dest='port', type='int', default=12345)
parser.add_option('-m', dest='msg')
(options, args) = parser.parse_args()


# run function makes TCP connection to Server
def run(host=options.ip, port=options.port):
    s = socket.socket()
    try:
        s.connect((host, port))
        s.sendall(options.msg)

    finally:
        s.close()

if __name__ == '__main__':
  run()
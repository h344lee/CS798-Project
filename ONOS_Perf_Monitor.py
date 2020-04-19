#!/usr/bin/python

"""
CS798-001, Advanced Network Architetures, Winter 2020
CS798-002, Network Softwarization, Winter 2020
Project

Department of Computer Science
Faculty of Mathematics
University of Waterloo
"""

__author__ = "Hoyoun Lee"
__email__ = "hoyoun.lee@uwaterloo.ca"

from mininet.node import RemoteController
from mininet.net import Mininet
from mininet.log import lg
import requests
import random
import paramiko
import multiprocessing
from multiprocessing import Process
import matplotlib.animation as animation
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn import preprocessing
from sklearn.svm import SVR
import time


# getFlowProcessPerSecond function request PACKET_IN / PACKET_OUT / FLOW_MOD rate to ONOS controller thtough REST API
# ONOS controller can provide those values by Control Plane Management Application (CPMON) application in ONOS
# Return : How many Packet In messages received and processed by controller within the last one minutes
def getFlowProcessPerSecond():

    resp = requests.get('http://localhost:8181/onos/v1/devices', auth=('onos', 'rocks'))
    if resp.status_code != 200:
        # This means something went wrong.
        print('getReponse() : something is wrong')

    info = resp.json()
    switchList = []
    for i in range(len(info['devices'])):
        switchList.append(info['devices'][i]['id'])

    packetInAPI = ['http://localhost:8181/onos/v1/metrics/' + switch + '.PACKET_IN.rate' for switch in switchList]
    packetOutAPI = ['http://localhost:8181/onos/v1/metrics/' + switch + '.PACKET_OUT.rate' for switch in switchList]
    flowModAPI = ['http://localhost:8181/onos/v1/metrics/' + switch + '.FLOW_MOD.rate' for switch in switchList]

    packetIn = []
    packetOut = []
    flowMod = []
    for i in range(len(switchList)):
        packetInResp = requests.get(packetInAPI[i], auth=('onos', 'rocks'))
        packetOutResp = requests.get(packetOutAPI[i], auth=('onos', 'rocks'))
        flowModResp = requests.get(flowModAPI[i], auth=('onos', 'rocks'))

        if resp.status_code != 200:
            # This means something went wrong.
            print('getReponse() : something is wrong')
        packetInInfo = packetInResp.json()
        packetOutInfo = packetOutResp.json()
        flowModInfo = flowModResp.json()

        # Flow Processes for last one minute
        packetIn.append(float(packetInInfo['metric'][switchList[i] + '.PACKET_IN.rate']['meter']['1_min_rate']))
        packetOut.append(float(packetOutInfo['metric'][switchList[i] + '.PACKET_OUT.rate']['meter']['1_min_rate']))
        flowMod.append(float(flowModInfo['metric'][switchList[i] + '.FLOW_MOD.rate']['meter']['1_min_rate']))


    #return (sum(flowMod) + sum(packetOut) - sum(packetIn))
    return sum(packetIn)


# getThroughput function request throughput of each switches to ONOS controller through REST API
# Return : How many amount of data is processed per second under ONOS controller (sum of TX and RX of every port of every switch)
def getThroughput() :
    throughtputAPI = 'http://localhost:8181/onos/v1/statistics/ports/'

    bytesReceived = []
    bytesSent = []
    throuputResp = requests.get(throughtputAPI, auth=('onos', 'rocks'))

    if throuputResp.status_code != 200:
        # This means something went wrong.
        print('getReponse() : something is wrong')
    throuputInfo = throuputResp.json()

    for i in range(len(throuputInfo['statistics'])):
        for j in range(len(throuputInfo['statistics'][i]['ports'])):
            bytesReceived.append(float(throuputInfo['statistics'][i]['ports'][j]['bytesReceived']))
            bytesSent.append(float(throuputInfo['statistics'][i]['ports'][j]['bytesSent']))

    return ((sum(bytesReceived) + sum(bytesSent)) / 1024)


# getSSHSession function utilize paramiko package to get SSH Session of ONOS controller
# Return : return ONOS controller ssh session
def getSSHSession(targetIP, username, password):

    sshSession = paramiko.SSHClient()
    sshSession.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    while True:
        try:
            sshSession.connect(targetIP, username = username, password = password)
            break
        except Exception as e:
            time.sleep(5)

    return sshSession


# runCommandOverSSH function deliver command to SSH session
# Return : output value and error (if there is an error) of the command
def runCommandOverSSH(sshSession, command):
    assert type(sshSession) is paramiko.client.SSHClient,\
            "'sshSession' is type %s" % type(sshSession)
    assert type(command) in (str, unicode), "'command' is type %s" % type(command)

    try:
        stdin, stdout, stderr = sshSession.exec_command(command)

        # Wait for command to finish (may take a while for long commands)
        while not stdout.channel.exit_status_ready() or \
                not stderr.channel.exit_status_ready():
            time.sleep(1)
    except Exception as e:
        return None

    else:
        err = stderr.readlines()
        err = ''.join(err) # Convert to single string
        if err:
            print('error is %s' %err)

        out = stdout.readlines()
        out = ''.join(out) # Convert to single string

        return (out, err)


# run function artificially make new TCP connections between Mininet nodes for duration value
# argument 1 : a list which contain a number of Mininet nodes
# argument 2 : an integer which is duration of run function would work
# argument 3 : an integer (min: 1, max: 20) which shows many many new TCP connections will occur.
# example 1 : 10 new TCP connections per second for 10 seconds => it needs at least math.sqrt(10*10) hosts (10 hosts)
# example 2 : 4 new TCP connections per second for 20 seconds => it needs at least math.sqrt(4*20) hosts (9 hosts)
def run(hosts, duration, newConnectionPS):
    counter = 0
    portNum = random.randint(49152, 65535)
    print("This flow will connect new connections at " + str(newConnectionPS) + "/s speed for " + str(duration) +" seconds")
    start = time.time()

    for i in hosts:
        p1 = i.popen('python myServer.py -i %s -p %i &' % (i.IP(), portNum))
        time.sleep(0.01)
        for j in hosts:
            j.cmd('python myClient.py -i %s -p %i -m "1"' % (i.IP(), portNum))
            counter += 1
            if counter%newConnectionPS == 0:
                time.sleep(1-0.033*newConnectionPS-0.01)
            if time.time() - start >= duration:
                break
        p1.terminate()
        if time.time() - start >= duration:
            break

    print("flow finished")


# dataCollect function collect CPU usage, Packet In value via getFlowProcessPerSecond, and MB/s throughput value via getThroughput function.
# After collect all data, it save the values to perfData.csv file concurrently.
def dataCollect(duration):

    controllerSSH = getSSHSession('localhost', 'hoyoun', 'hoyoun')

    cpuUsage = []
    FlowPS = []
    MBPS = []

    oldFlowPS = getFlowProcessPerSecond()
    oldMBPS = getThroughput()

    perfData = pd.DataFrame(columns = ['Seconds', 'CPU', 'Packet In', 'MB/s'])

    iter = duration / 5

    for i in range(iter):
        cmd = "mpstat 1 5 | awk '/Average:/' | awk '{print $12}' "
        out, err = runCommandOverSSH(controllerSSH, cmd)
        cpuUsage.append(round(100 - float(out),2))

        newFlowPS = getFlowProcessPerSecond()
        FlowPS.append(round((newFlowPS - oldFlowPS)/5.2,2))
        oldFlowPS = newFlowPS

        newMBPS = getThroughput()
        MBPS.append(round((newMBPS-oldMBPS)/5.2,2))
        oldMBPS = newMBPS

        perfData.loc[i] = [(i+1)*5, cpuUsage[i], FlowPS[i], MBPS[i] ]
        perfData.to_csv('perfData.csv')



#perfPlot Class displays 6 kind of different data in real time
#1. real time cpu usage
#2. predicted cpu usage by Support Vector Machine regression
#3. monitoring interval in the display. (min: 5 seconds, max :10 seconds)
#4. new TCP connections per second in real time
#5. throughput of network under ONOS in real time
#6. Packet In per second in real time

class perfPlot(multiprocessing.Process):
    def __init__(self, duration, scenario):
        super(perfPlot, self).__init__()
        self.scenario = scenario
        self.duration = duration
        self.ani = None
        self.fig = plt.figure(figsize=(12,8))

        self.ax1 = self.fig.add_subplot(2, 3, 1)
        self.ax2 = self.fig.add_subplot(2, 3, 2)
        self.ax3 = self.fig.add_subplot(2, 3, 3)
        self.ax4 = self.fig.add_subplot(2, 3, 4)
        self.ax5 = self.fig.add_subplot(2, 3, 5)
        self.ax6 = self.fig.add_subplot(2, 3, 6)

        self.x = []
        self.y = []
        self.y2 = []
        self.y3 = []
        self.y4 = []
        self.y5 = []
        self.y6 = []

        self.ln, = self.ax1.plot(self.x, self.y, 'b-o')
        self.ln2, = self.ax2.plot(self.x, self.y2, 'g-*')
        self.ln3, = self.ax3.plot(self.x, self.y3, 'r-x')
        self.ln4, = self.ax4.plot(self.x, self.y4, 'c-v')
        self.ln5, = self.ax5.plot(self.x, self.y5, 'm-+')
        self.ln6, = self.ax6.plot(self.x, self.y6, 'y-+')

        self.curInterval = 7500
        self.maxInterval = 10000
        self.minInterval = 5000
        self.newInterval = 7500
        self.predictedCPU = 0
        self.startTime = time.time()
        self.ani = animation.FuncAnimation(self.fig, self.animate, interval=7500, init_func=self.plotInit)
        print("plot show!")
        plt.show()


    # plotInit method set initial plot configurations
    def plotInit(self):

        x_major_ticks = np.arange(0, 121, 20)
        x_minor_ticks = np.arange(0, 121, 5)

        y_major_ticks = np.arange(0, 101, 20)
        y_minor_ticks = np.arange(0, 101, 5)

        y3_major_ticks = np.arange(0, 11, 1)
        y3_minor_ticks = np.arange(0, 11, 0.5)

        y4_major_ticks = np.arange(0, 21, 5)
        y4_minor_ticks = np.arange(0, 21, 1)

        y5_major_ticks = np.arange(0, 41, 5)
        y5_minor_ticks = np.arange(0, 41, 1)

        y6_major_ticks = np.arange(0, 351, 50)
        y6_minor_ticks = np.arange(0, 351, 10)

        axList = [self.ax1, self.ax2, self.ax3, self.ax4, self.ax5, self.ax6]

        for i in axList:
            i.set_xticks(x_major_ticks)
            i.set_xticks(x_minor_ticks, minor=True)

            i.grid(which='both')
            i.grid(which='minor', alpha=0.2)
            i.grid(which='major', alpha=0.5)

            i.set_xlabel('Seconds')

        self.ax1.set_yticks(y_major_ticks)
        self.ax1.set_yticks(y_minor_ticks, minor=True)
        self.ax1.set_ylabel('CPU Usage(%)')
        self.ax1.set_title('ONOS Controller CPU Usage')

        self.ax2.set_yticks(y_major_ticks)
        self.ax2.set_yticks(y_minor_ticks, minor=True)
        self.ax2.set_ylabel('CPU Usage(%)')
        self.ax2.set_title('ML Predicted CPU Usage')

        self.ax3.set_yticks(y3_major_ticks)
        self.ax3.set_yticks(y3_minor_ticks, minor=True)
        self.ax3.set_ylabel('Interval(Seconds)')
        self.ax3.set_title('ONOS Performance Monitoring Interval')

        self.ax4.set_yticks(y4_major_ticks)
        self.ax4.set_yticks(y4_minor_ticks, minor=True)
        self.ax4.set_ylabel('New Connections/s')
        self.ax4.set_title('ONOS Traffic Scenario (New TCP Connection/s)')

        self.ax5.set_yticks(y5_major_ticks)
        self.ax5.set_yticks(y5_minor_ticks, minor=True)
        self.ax5.set_ylabel('MB/s')
        self.ax5.set_title('ONOS Network Throughput (MB/s)')

        self.ax6.set_yticks(y6_major_ticks)
        self.ax6.set_yticks(y6_minor_ticks, minor=True)
        self.ax6.set_ylabel('Packet In/s')
        self.ax6.set_title('ONOS Traffic Scenario (Packet In/s)')

        self.fig.tight_layout()


    # animate function collect all the data and set the data to the display at variable interval value
    # after getting initial data to run machine learning (26 seconds), it run the Support Vector Machine Regression to
    # predict next CPU usage, and change the interval based on CPU usage
    def animate(self, i):

        self.x.append(round(time.time() - self.startTime,1))
        self.y.append(pd.read_csv('perfData.csv')[['CPU']].values.tolist()[-1])
        self.y2.append(self.predictedCPU)
        self.y3.append(round(self.newInterval/1000.0,1))
        self.y4.append(self.scenario[int(self.x[-1])])
        self.y5.append(pd.read_csv('perfData.csv')[['MB/s']].values.tolist()[-1])
        self.y6.append(pd.read_csv('perfData.csv')[['Packet In']].values.tolist()[-1])

        self.ln.set_data(self.x, self.y)
        self.ln2.set_data(self.x, self.y2)
        self.ln3.set_data(self.x, self.y3)
        self.ln4.set_data(self.x, self.y4)
        self.ln5.set_data(self.x, self.y5)
        self.ln6.set_data(self.x, self.y6)

         # start after 26 seconds to get enough data
        if time.time() - self.startTime >= 30:
            self.changePlotInterval()
        if time.time() - self.startTime >= self.duration:
            self.ani.event_source.stop()


    #if predicted CPU usage is over 40, the data collection interval getting 15 percent longer
    #if the predictied CPU usage is under 40, the interval getting 5 percent shorter
    def changePlotInterval(self):
        self.predictedCPU = SVRRegression()

        if self.predictedCPU >= 40 and (self.curInterval) <= self.maxInterval:
            if int(self.curInterval * 1.15) >= self.maxInterval:
                self.newInterval = self.maxInterval
            else :
                self.newInterval = int(self.curInterval * 1.15)

        elif self.predictedCPU <= 40 and (self.curInterval) >= self.minInterval:
            if int(self.curInterval *0.95) <= self.minInterval:
                self.newInterval = self.minInterval
            else :
                self.newInterval = int(self.curInterval * 0.95)

        else :
            self.newInterval = self.curInterval

        if self.newInterval != self.curInterval :
            self.ani.event_source.interval = self.newInterval

        self.curInterval = self.newInterval


# reconstruct_val function reconstruct from scaled version of data prediction to original version of data prediction value
# Return : predicted value of original data scale
def reconstruct_val(scaler, pre, prd):
    if (pre.size != prd.size):
        print('Lengths of the arguments (time-series) are not the same.')
        return None

    tmp1 = pre.values.reshape(pre.size, 1) + prd.reshape(pre.size, 1)
    tmp2 = scaler.inverse_transform(tmp1)

    return tmp2[0][0]


# def LSTMRegression():
#
#     data = pd.read_csv('perfData.csv')[['CPU']]
#     scaler = preprocessing.MinMaxScaler(feature_range=(-1, 1))
#     data['SCALED'] = scaler.fit_transform(data['CPU'].values.reshape(data.shape[0], 1))
#
#     data['DIFF'] = data['SCALED'].diff().fillna(0)
#     data['SCALED_SHIFT'] = data['SCALED'].shift(1).fillna(0)
#
#     feature_dimension = 5
#     for i in range(1, feature_dimension + 1):
#         data['FEATURE_' + str(i)] = data['DIFF'].shift(i).fillna(0)
#
#     data['LABEL'] = data['DIFF']
#     split_index = int(round(data.shape[0] * 0.8))
#
#     train_num = split_index
#     test_num = int(round(data.shape[0])) - split_index
#
#     features = ['FEATURE_' + str(i) for i in range(1, feature_dimension + 1)]
#     label = 'LABEL'
#
#     train_x = data[features].iloc[split_index - train_num:split_index]
#     train_y = data[label].iloc[split_index - train_num:split_index]
#
#     test_x = data[features].iloc[split_index:split_index + test_num]
#     test_y = data[label].iloc[split_index:split_index + test_num]
#     test_pre = data['SCALED_SHIFT'].iloc[split_index:split_index + test_num]
#     test_orig = data['CPU'].iloc[split_index:split_index + test_num]
#     last_x = data[features].iloc[-1:]
#     last_pre = data['SCALED_SHIFT'].iloc[-1:]
#
#     # Modeling and Prediction using LSTM
#
#     # Reshape the data for LSTM model
#     train_lstm_x = train_x.values.reshape(train_x.shape[0], 1, train_x.shape[1])
#     test_lstm_x = test_x.values.reshape(test_x.shape[0], 1, test_x.shape[1])
#
#     # Train the model
#     neurons = 600
#     batch_size = train_num
#     epochs = 200
#
#     reg_lstm = Sequential()
#     reg_lstm.add(LSTM(neurons, input_shape=(train_lstm_x.shape[1], train_lstm_x.shape[2])))
#     reg_lstm.add(Dense(1))
#     reg_lstm.compile(loss='mean_squared_error', optimizer='adam')
#     reg_lstm.fit(train_lstm_x, train_y, epochs=epochs, batch_size=batch_size, shuffle=False,
#                  verbose=0, validation_data=(test_lstm_x, test_y))
#
#     # Predict test samples
#     test_lstm_x2 = last_x.values.reshape(last_x.shape[0], 1, last_x.shape[1])
#     pre = reg_lstm.predict(test_lstm_x2, batch_size=batch_size)
#     prediction = reconstruct_val(scaler, last_pre, pre)
#
#     return(round(prediction,2))



#perform SVM Regression based on given last 5 cpu usage data
#Return : prediction value of next CPU usage value
def SVRRegression():

        data = pd.read_csv('perfData.csv')[['CPU']]
        scaler = preprocessing.MinMaxScaler(feature_range=(-1, 1))
        data['SCALED'] = scaler.fit_transform(data['CPU'].values.reshape(data.shape[0], 1))

        data['DIFF'] = data['SCALED'].diff().fillna(0)
        data['SCALED_SHIFT'] = data['SCALED'].shift(1).fillna(0)

        feature_dimension = 5
        for i in range(1, feature_dimension + 1):
            data['FEATURE_' + str(i)] = data['DIFF'].shift(i).fillna(0)

        data['LABEL'] = data['DIFF']
        split_index = int(round(data.shape[0] * 0.8))

        train_num = split_index
        test_num = int(round(data.shape[0])) - split_index

        features = ['FEATURE_' + str(i) for i in range(1, feature_dimension + 1)]
        label = 'LABEL'

        #    print(data)
        train_x = data[features].iloc[split_index - train_num:split_index]
        train_y = data[label].iloc[split_index - train_num:split_index]

        test_x = data[features].iloc[split_index:split_index + test_num]
        last_x = data[features].iloc[-1:]
        last_pre = data['SCALED_SHIFT'].iloc[-1:]

        reg = SVR(kernel='sigmoid', epsilon=0.05)
        reg.fit(train_x, train_y)

        pre = reg.predict(last_x.values)
        prediction = reconstruct_val(scaler, last_pre, pre)

        return (round(prediction, 2))


# setup Mininet environment
# 3 switches and 20 hosts to each switches (total 60 hosts)
def startMininet():
    lg.setLogLevel('info')

    net = Mininet(autoSetMacs=True, cleanup=True)

    # Create the network switches
    s1, s2, s3 = [net.addSwitch(s) for s in 's1', 's2', 's3']

    # Create network hosts
    h1, h2, h3, h4, h5, h6, h7, h8, h9, h10, h11, h12, h13, h14, h15, h16, h17, h18, h19, h20, \
    h21, h22, h23, h24, h25, h26, h27, h28, h29, h30, h31, h32, h33, h34, h35, h36, h37, h38, h39, h40, \
    h41, h42, h43, h44, h45, h46, h47, h48, h49, h50, h51, h52, h53, h54, h55, h56, h57, h58, h59, h60 = \
        [net.addHost(h, cpu=0.05) for h in 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'h7', 'h8', 'h9', 'h10',
                                           'h11', 'h12', 'h13', 'h14', 'h15', 'h16', 'h17', 'h18', 'h19', 'h20',
                                           'h21', 'h22', 'h23', 'h24', 'h25', 'h26', 'h27', 'h28', 'h29', 'h30',
                                           'h31', 'h32', 'h33', 'h34', 'h35', 'h36', 'h37', 'h38', 'h39', 'h40',
                                           'h41', 'h42', 'h43', 'h44', 'h45', 'h46', 'h47', 'h48', 'h49', 'h50',
                                           'h51', 'h52', 'h53', 'h54', 'h55', 'h56', 'h57', 'h58', 'h59', 'h60']

    c1 = RemoteController('c1', ip='127.0.0.1', port=6633)
    net.addController(c1)

    # Add link between switches.
    net.addLink(s1, s2)
    net.addLink(s2, s3)

    for (h, s) in [(h1, s1), (h2, s1), (h3, s1), (h4, s1), (h5, s1), (h6, s1), (h7, s1), (h8, s1), (h9, s1), (h10, s1),
                   (h11, s1), (h12, s1), (h13, s1), (h14, s1), (h15, s1), (h16, s1), (h17, s1), (h18, s1), (h19, s1), (h20, s1),
                   (h21, s2), (h22, s2), (h23, s2), (h24, s2), (h25, s2), (h26, s2), (h27, s2), (h28, s2), (h29, s2), (h30, s2),
                   (h31, s2), (h32, s2), (h33, s2), (h34, s2), (h35, s2), (h36, s2), (h37, s2), (h38, s2), (h39, s2), (h40, s2),
                   (h41, s3), (h42, s3), (h43, s3), (h44, s3), (h45, s3), (h46, s3), (h47, s3), (h48, s3), (h49, s3), (h50, s3),
                   (h51, s3), (h52, s3), (h53, s3), (h54, s3), (h55, s3), (h56, s3), (h57, s3), (h58, s3), (h59, s3), (h60, s3)]:
        net.addLink(h, s)

    net.start()

    return net, [h1, h2, h3, h4, h5, h6, h7, h8, h9, h10, h11, h12, h13, h14, h15, h16, h17, h18, h19, h20, \
             h21, h22, h23, h24, h25, h26, h27, h28, h29, h30, h31, h32, h33, h34, h35, h36, h37, h38, h39, h40, \
             h41, h42, h43, h44, h45, h46, h47, h48, h49, h50, h51, h52, h53, h54, h55, h56, h57, h58, h59, h60]


# main function which orchestrates Mininet setup, workload generation, data collection and data visualization based on machine learning based CPU usage prediction
def main():

    net, hosts = startMininet()

    # sleep for 180 second to get an accurate Packet In statistics
    time.sleep(180)

    # setup for four flow to get scenario of total workload
    flow1 = [1] * 120
    flow2 = [0] * 30 + [2] * 90
    flow3 = [0] * 60 + [8] * 60
    flow4 = [0] * 90 + [4] * 30
    scenario = [sum(x) for x in zip(flow1, flow2, flow3, flow4)]

    # process for collect statistics data
    proc0 = Process(target=dataCollect, args=(125,))
    proc0.start()
    time.sleep(5)

    # process to plot collected data
    proc10 = Process(target=perfPlot, args=(120,scenario))
    proc10.start()

    # flow start
    start_time = time.time()

    # set workload1 which generate 1 new TCP connections per second for 120 seconds
    proc1 = Process(target=run, args=(hosts[:11], 120, 1))
    proc1.start()
    time.sleep(30)

    # set workload2 which generate 2 new TCP connections per second for 90 seconds
    proc2 = Process(target=run, args=(hosts[11:25], 90, 2))
    proc2.start()
    time.sleep(30)

    # set workload3 which generate 8 new TCP connections per second for 60 seconds
    proc3 = Process(target=run, args=(hosts[25:47], 60, 8))
    proc3.start()
    time.sleep(30)

    # set workload1 which generate 4 new TCP connections per second for 30 seconds
    proc4 = Process(target=run, args=(hosts[47:], 30, 4))
    proc4.start()
    time.sleep(30)

    print("test duration : " + str(time.time() - start_time))

    proc1.join()
    proc2.join()
    proc3.join()
    proc4.join()

    proc0.join()
    proc10.join()

    net.stop()

if __name__ == '__main__':
    main()

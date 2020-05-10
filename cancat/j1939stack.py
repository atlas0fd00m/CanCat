from cancat.j1939 import *
# we can move things into here if we decide this replaces the exiting j1939 modules

''' 
This is a J1939 Stack module.
It's purpose is to provide a J1939-capable object which extends (consumes) CanCat's CanInterface module, and provides a J1939 interface.
In the original J1939 module, extended messages were treated like oddities.  This module will work on the premise that all messages (except TP messages) are created equal, and are available in the same queue.  TP messages will be the "specialty" messages which create new, arbitrary sized messages from smaller ones.  If they don't make it through, they don't.  This module is intended to make J1939 attack clients easier to work with, whereas the first module was focused on reverse engineering.  Let's see if we can't come up with something awesome, then possible merge them together in the future.

This module focuses around PGNs.  All messages are handled and sorted by their PS/DA.
'''

J1939MSGS = 1939

class J1939Interface(cancat.CanInterface):
    def __init__(self, port=None, baud=baud, verbose=False, cmdhandlers=None, comment='', load_filename=None, orig_iface=None):
        self.myIDs = []
        self._last_recv_idx = -1
        self._threads = []
        self._j1939_filters = []
        self._j1939_msg_events = {}
        self._j1939queuelock = threading.Lock()
        self._TPmsgParts = {}
        self.maxMsgsPerPGN = 0x200
        self._j1939_msg_listeners = []
        self.promisc = False
        #self._msg_source_idx = J1939MSGS    # FIXME: take us back to using standard _messages with this as the key

        CanInterface.__init__(self, port=port, baud=baud, verbose=verbose, cmdhandlers=cmdhandlers, comment=comment, load_filename=load_filename, orig_iface=orig_iface)

        # setup the message handler event offload thread
        self._mhe_queue = Queue.Queue()
        mhethread = threading.Thread(target=self._mhe_runner)
        mhethread.setDaemon(True)
        mhethread.start()
        self._threads.append(mhethread)

        self.register_handler(CMD_CAN_RECV, self._j1939_can_handler)

    def setPromiscuous(self, promisc=True):
        '''
        Determines whether messages not destined for an ID I currently own (self.myIDs) are kept/handled or discarded
        '''
        self.promisc = promisc

    def addID(self, newid):
        if newid not in self.myIDs:
            self.myIDs.append(newid)

    def delID(self, curid):
        if curid in self.myIDs:
            self.myIDs.remove(curid)

    def J1939xmit(self, pf, ps, sa, data, prio=6, edp=0, dp=0):
        if len(data) < 8:
            arbid = emitArbid(prio, edp, dp, pf, ps, sa)
            # print "TX: %x : %r" % (arbid, data.encode('hex'))
            self.CANxmit(arbid, data, extflag=1)
            return

        self._j1939xmit_tp(pf, ps, sa, data, prio, edp, dp)

    def _j1939xmit_tp(self, pf, ps, sa, message, prio=6, edp=0, dp=0):
        pgn2 = (edp << 1) | dp
        pgn1 = pf
        if pgn1 < 240:
            pgn0 = 0
        else:
            pgn0 = ps

        msgs = ['%c'%(x+1) + message[x*7:(x*7)+7] for x in range((len(message)+6)/7)]
        if len(msgs) > 255:
            raise Exception("J1939xmit_tp: attempt to send message that's too large")

        cm_msg = struct.pack('<BHBBBBB', CM_RTS, len(message), len(msgs), 0xff, 
                pgn2, pgn1, pgn0)

        arbid = emitArbid(prio, edp, dp, PF_TP_CM, ps, sa)
        # print "TXe: %x : %r" % (arbid, cm_msg.encode('hex'))
        self.CANxmit(arbid, cm_msg, extflag=1)
        time.sleep(.01)  # hack: should watch for CM_CTS
        for msg in msgs:
            #self.J1939xmit(PF_TP_DT, ps, sa, msg, prio=prio)
            arbid = emitArbid(prio, edp, dp, PF_TP_DT, ps, sa)
            print "TXe: %x : %r" % (arbid, msg.encode('hex'))
            self.CANxmit(arbid, msg, extflag=1)

        # hack: should watch for CM_EOM

    #def _reprCanMsg(self, idx, ts, arbid, data, comment=None):
    def _reprCanMsg(self, *args, **kwargs):
        '''
        FIXME later
        '''
        print "_reprCanMsg: %r   %r" % (args, kwargs)
        return

        if comment == None:
            comment = ''

        arbtup = parseArbid(arbid)
        prio, edp, dp, pf, ps, sa = arbtup

        # give name priority to the Handler, then the manual name (this module), then J1939PGNdb
        pfmeaning, handler = pgn_pfs.get(pf, ('',None))
        nextline = ''

        if handler != None:
            enhanced = handler(idx, ts, arbtup, data, self)
            if enhanced == cancat.DONT_PRINT_THIS_MESSAGE:
                return enhanced

            if enhanced != None:
                if type(enhanced) in (list, tuple) and len(enhanced):
                    pfmeaning = enhanced[0]
                    if len(enhanced) > 1:
                        nextline = '\n'.join(list(enhanced[1:]))

                    # if we get multiple lines and the first is DONT_PRINT_THIS_MESSAGE, 
                    # then just return nextline
                    if pfmeaning == cancat.DONT_PRINT_THIS_MESSAGE:
                        return nextline

                    nextline = '\n' + nextline

                else:
                    pfmeaning = enhanced

        elif not len(pfmeaning):
            pgn = (pf<<8) | ps
            res = J1939PGNdb.get(pgn)
            if res == None:
                res = J1939PGNdb.get(pf<<8)
            if res != None:
                pfmeaning = res.get("Name")

        return "%.8d %8.3f pri/edp/dp: %d/%d/%d, PG: %.2x %.2x  Source: %.2x  Data: %-18s  %s\t\t%s%s" % \
                (idx, ts, prio, edp, dp, pf, ps, sa, data.encode('hex'), pfmeaning, comment, nextline)

    def _j1939_can_handler(self, message, none):
        '''
        this function is run for *Every* received CAN message... and is executed from the 
        XMIT/RECV thread.  it *must* be fast!
        '''
        #print repr(self), repr(cmd), repr(message)
        arbid, data = self._splitCanMsg(message)
        arbtup = parseArbid(arbid)
        prio, edp, dp, pf, ps, sa = arbtup

        # if i don't care about this message... bail. (0xef+ is multicast)
        if pf < 0xef and ps not in self.myIDs and not self.promisc:
            return

        if pf == 0xeb:
            self.queueMessageHandlerEvent(self.eb_handler, arbtup, data)
        elif pf == 0xec:
            self.queueMessageHandlerEvent(self.ec_handler, arbtup, data)
        else:
            self.queueMessageHandlerEvent(self._submitJ1939Message, arbtup, data)

        #print "submitted message: %r" % (message.encode('hex'))


    def queueMessageHandlerEvent(self, pfhandler, arbtup, data):
        ''' 
        this is run in the XMIT/RECV thread and is intended to handle offloading the data fast
        '''
        self._mhe_queue.put((pfhandler, arbtup, data))

    def _mhe_runner(self):
        ''' 
        runs the mhe thread, which is offloaded so that the message-handling thread can keep going
        '''
        while self._go:
            worktup = None
            try:
                worktup = self._mhe_queue.get(1)
                if worktup == None:
                    continue

                pfhandler, arbtup, data = worktup
                pfhandler(arbtup, data)

            except Exception, e:
                print "MsgHandler ERROR: %r (%r)" % (e, worktup)
                if self.verbose:
                    sys.excepthook(*sys.exc_info())

    def _submitJ1939Message(self, arbtup, message):
        '''
        submits a message to the cmd mailbox.  creates mbox if doesn't exist.
        *threadsafe*
        often runs in the MHE thread
        '''
        timestamp = time.time()
        prio, edp, dp, pf, ps, sa = arbtup
        pgn = (pf<<8) | ps
        datarange = (edp<<1) | dp

        if len(self._j1939_filters):
            lcls = locals()
            for advf in self._j1939_filters:
                try:
                    if not eval(advf, lcls):
                        return
                except Exception, e:
                    print "_submitJ1939Message advfilter ERROR: %r" % e
                    return

        self._j1939queuelock.acquire()
        try:
            # do we want to break things apart into PGN mboxes at this point?  if so, we have to also allow 
            # subscription at this level for things like sniffing.  Like this:
            handled = False
            for listener in self._j1939_msg_listeners:
                try:
                    contnu = listener(arbtup, message)
                    if contnu: 
                        handled = True

                except Exception, e:
                    self.log('_submitJ1939Message: ERROR: %r' % e)
            
            if handled:
                return

            ##::: TODO, make this a listener.  if at all...
            #dr = self._messages.get(datarange)
            #if dr == None:
                #dr = {}
                #self._messages[datarange] = dr
            #
            ## factor in multicast vs. unicast...
            #mbox = dr.get(pf)
            #if mbox == None:
                #mbox = []
                #dr[pf] = mbox
                #self._j1939_msg_events[pf] = threading.Event()

            mbox = self._messages.get(J1939MSGS)
            if mbox == None:
                mbox = []
                self._messages[J1939MSGS] = mbox

            msgevt = self._j1939_msg_events.get(J1939MSGS)
            if msgevt == None:
                msgevt = threading.Event()
                self._j1939_msg_events[J1939MSGS] = msgevt

            #mbox.append((pf, ps, sa, edp, dp, prio, timestamp, message))
            mbox.append((timestamp, arbtup, message))
            msgevt.set()
            ##self._j1939_msg_events[pf].set()
            # note: this event will trigger for any of the data ranges, as long as the PF is correct... this may be a problem.
            # FIXME: come back to this...

        except Exception, e:
            self.log("_submitMessage: ERROR: %r" % e, -1)
            if self.verbose:
                sys.excepthook(*sys.exc_info())

        finally:
            self._j1939queuelock.release()

    def getJ1939MsgCount(self):
        j1939Msgs = self._messages.get(J1939MSGS)
        if j1939Msgs is None:
            return 0
        return len(j1939Msgs)

    def subscribe(self, msg_handler):
        if msg_handler not in self._j1939_msg_listeners:
            self._j1939_msg_listeners.append(msg_handler)

    def unsubscribe(self, msg_handler):
        if msg_handler in self._j1939_msg_listeners:
            self._j1939_msg_listeners.remove(msg_handler)

    def ec_handler(j1939, arbtup, data):
        '''
        special handler for TP_CM messages
        '''
        def tp_cm_10(arbtup, data, j1939):     # RTS
            (prio, edp, dp, pf, da, sa) = arbtup

            (cb, totsize, pktct, maxct,
                    pgn2, pgn1, pgn0) = struct.unpack('<BHBBBBB', data)
            
            # check for old stuff
            extmsgs = j1939.getTPmsgParts(da, sa)
            if extmsgs != None and len(extmsgs['msgs']):
                extmsgs['sa'] = sa
                extmsgs['da'] = da
                j1939.saveTPmsgs(sa, da, (0,0,0), meldExtMsgs(extmsgs), TP_DIRECT_BROKEN)
                j1939.clearTPmsgParts(da, sa)

            # store extended message information for other stuff...
            extmsgs = j1939.getTPmsgParts(da, sa, create=True)
            extmsgs['sa'] = sa
            extmsgs['da'] = da
            extmsgs['pgn2'] = pgn2
            extmsgs['pgn1'] = pgn1
            extmsgs['pgn0'] = pgn0
            extmsgs['maxct'] = maxct
            extmsgs['length'] = pktct
            extmsgs['totsize'] = totsize
            extmsgs['type'] = TP_DIRECT
            extmsgs['adminmsgs'].append((arbtup, data))

            # RESPOND!
            if da in j1939.myIDs:
                response = struct.pack('<BBBHBBB', CM_CTS, pktct, 1, 0, pgn2, pgn1, pgn0)
                j1939.J1939xmit(0xec, sa, da, response, prio)

        def tp_cm_11(arbtup, data, j1939):     # CTS
            (prio, edp, dp, pf, da, sa) = arbtup

            (cb, maxpkts, nextpkt, reserved,
                    pgn2, pgn1, pgn0) = struct.unpack('<BBBHBBB', data)

            # store extended message information for other stuff...
            extmsgs = j1939.getTPmsgParts(da, sa)
            if extmsgs is None:
                return

            extmsgs['adminmsgs'].append((arbtup, data))

            # SOMEHOW WE TRIGGER THE CONTINUATION OF TRANSMISSION

        def tp_cm_13(arbtup, data, j1939):     # EOM
            (prio, edp, dp, pf, da, sa) = arbtup

            (cb, totsize, pktct, maxct,
                    pgn2, pgn1, pgn0) = struct.unpack('<BHBBBBB', data)

            # print out extended message and clear the buffers.
            extmsgs = j1939.getTPmsgParts(da, sa)
            if extmsgs is None:
                return 

            extmsgs['adminmsgs'].append((arbtup, data))

            j1939.clearTPmsgParts(da, sa)
            # Coolio, they just confirmed receipt, we're done!
            # Probably need to trigger some mechanism telling the originator

        def tp_cm_20(arbtup, data, j1939):     # BROADCAST MESSAGE (BAM)
            (prio, edp, dp, pf, da, sa) = arbtup

            (cb, totsize, pktct, reserved,
                    pgn2, pgn1, pgn0) = struct.unpack('<BHBBBBB', data)

            # check for old stuff
            extmsgs = j1939.getTPmsgParts(da, sa)
            if extmsgs != None and len(extmsgs['msgs']):
                extmsgs['sa'] = sa
                extmsgs['da'] = da
                j1939.saveTPmsgs(sa, da, (0,0,0), meldExtMsgs(extmsgs), TP_DIRECT_BROKEN)

            j1939.clearTPmsgParts(da, sa)

            # store extended message information for other stuff...
            extmsgs = j1939.getTPmsgParts(sa, da, create=True)
            extmsgs['sa'] = sa
            extmsgs['da'] = da
            extmsgs['pgn2'] = pgn2
            extmsgs['pgn1'] = pgn1
            extmsgs['pgn0'] = pgn0
            extmsgs['maxct'] = 0
            extmsgs['length'] = pktct
            extmsgs['totsize'] = totsize
            extmsgs['type'] = TP_BAM
            extmsgs['adminmsgs'].append((arbtup, data))

        # call the right TP_CM handler
        tp_cm_handlers = {
                CM_RTS:     ('RTS',           tp_cm_10),
                CM_CTS:     ('CTS',           tp_cm_11),
                CM_EOM:     ('EndOfMsgACK',   tp_cm_13),
                CM_BAM:     ('BAM-Broadcast', tp_cm_20),
                CM_ABORT:   ('Abort',         None),
                }

        cb = ord(data[0])
        #print "ec: %.2x%.2x %.2x" % (arbtup[3], arbtup[4], cb)

        htup = tp_cm_handlers.get(cb)
        if htup != None:
            subname, cb_handler = htup

            if cb_handler != None:
                cb_handler(arbtup, data, j1939)

    def eb_handler(j1939, arbtup, data):
        '''
        special handler for TP_DT messages
        '''
        (prio, edp, dp, pf, da, sa) = arbtup
        if len(data) < 1:
            j1939.log('pf=0xeb: TP ERROR: NO DATA!')
            return

        extmsgs = j1939.getTPmsgParts(sa, da)
        if extmsgs is None:
            j1939.log("TP_DT: haven't received TP_CM control setup, skipping")
            return

        extmsgs['msgs'].append((arbtup, data))
        if len(extmsgs['msgs']) >= extmsgs['length']:
            # we're done building this message, submit it!
            #print "eb_handler: saving: %r %r" % (len(extmsgs['msgs']) , extmsgs['length'])
            pgn2 = extmsgs['pgn2']
            pgn1 = extmsgs['pgn1']
            pgn0 = extmsgs['pgn0']
            mtype = extmsgs['type']

            j1939.saveTPmsgs(sa, da, (pgn2, pgn1, pgn0), meldExtMsgs(extmsgs), mtype)
            j1939.clearTPmsgParts(da, sa)

            # if this is the end of a message to *me*, reply accordingly
            if da in j1939.myIDs:
                if mtype == None:
                    j1939.log("TP_DT_handler: missed beginning of message, not sending EOM: %r" % \
                            repr(extmsgs), 1)
                    return

                j1939.log("tp_stack: sending EOM  extmsgs: %r" % extmsgs, 1)
                pgn2 = extmsgs['pgn2']
                pgn1 = extmsgs['pgn1']
                pgn0 = extmsgs['pgn0']
                totsize = extmsgs['totsize']
                maxct = extmsgs['maxct']
                pktct = extmsgs['length']

                data = struct.pack('<BHBBBBB', CM_EOM, totsize, pktct, maxct, pgn2, pgn1, pgn0)
                j1939.J1939xmit(PF_TP_CM, sa, da,  data, prio=prio)

    # functions to support the J1939TP Stack (real stuff, not just repr)
    '''
    these functions support TP messaging.  Message parts are stored as PF lists within DA dicts within SA dicts.
    ie.:
        self_TPmsgParts[sa][da][pf]

    this allows for clearing of entire parts of the transient stack easily by SA.
    The main message stack has a *different* hierarchy based on what's easiest for developing client code to access.
    '''
    def getTPmsgParts(self, da, sa, create=False):
        '''
        # functions to support the J1939TP Stack (real stuff, not just repr)
        returns a message list for a given source and destination (sa, da)

        if no list exists for this pairing, one is created and an empty list is returned
        '''
        msglists = self._TPmsgParts.get(sa)
        if msglists == None:
            msglists = {}
            self._TPmsgParts[sa] = msglists

        mlist = msglists.get(da)
        if mlist == None and create:
            # create something new
            mlist = {'length':0, 
                    'msgs':[], 
                    'type':None, 
                    'adminmsgs':[], 
                    'pgn0':None, 
                    'pgn1':pf, 
                    'pgn2':None,   
                    'totsize':0,
                    'maxct':0xff,
                    'sa' : sa,
                    'da' : da,
                    }
            msglists[da] = mlist

        return mlist

    def clearTPmsgParts(self, da, sa):
        '''
        # functions to support the J1939TP Stack (real stuff, not just repr)
        clear out extended messages metadata.

        if da == None, this clears *all* message data for a given source address

        returns whether the thing deleted exists previously
        * if da == None, returns whether the sa had anything previously
        * otherwise, if the list 
        '''
        exists = False
        if da != None:
            msglists = self._TPmsgParts.get(sa)
            exists = bool(msglists != None and len(msglists))
            self._TPmsgParts[sa] = {}
            return exists

        msglists = self._TPmsgParts.get(sa)
        if msglists == None:
            msglists = {}
            self._TPmsgParts[sa] = msglists

        mlist = msglists.get(da, {'length':0})
        msglists[da] = {'length':0, 'msgs':[], 'type':None, 'adminmsgs':[]}
        return bool(mlist['length'])

    def saveTPmsg(self, sa, da, pgn, msg, tptype):
        '''
        # functions to support the J1939TP Stack (real stuff, not just repr)
        store a TP message.
        '''
        # FIXME: do we need thread-safety wrappers here?
        #msglist = self._TPmsgs.get((sa,da))
        #if msglist == None:
        #    msglist = []
        #    self._TPmsgs[(sa,da)] = msglist
        #
        #msglist.append((idx, ts, sa, da, pgn, msg, tptype, lastidx))
        arbtup = prio, edp, dp, pf, ps, sa = arbtup
        self._submitJ1939Message(arbtup, msg)

    def getCanMsgQueue(self):
        return self._messages.get(J1939MSGS)

    def genCanMsgs(self, start=0, stop=None, arbids=None, tail=False, maxsecs=None):
        '''
        CAN message generator.  takes in start/stop indexes as well as a list
        of desired arbids (list)

        maxsecs limits the number of seconds this generator will go for.  it's intended
        for use with tail
        '''

        messages = self.getCanMsgQueue()
        if messages == None and not tail:
            return

        # get the ts of the first received message
        if messages != None and len(messages):
            startts = messages[0][0]
        else:
            startts = time.time()

        if start == None:
            start = self.getJ1939MsgCount()

        if stop == None or tail:
            stop = len(messages)
        else:
            stop = stop + 1 # This makes the stop index inclusive if specified

        starttime = time.time()

        idx = start
        while tail or idx < stop:
            # obey our time restrictions
            # placed here to ensure checking whether we're receiving messages or not
            if maxsecs != None and time.time() > maxsecs+starttime:
                return
        
            # if we're off the end of the original request, and "tailing"
            if tail and idx >= stop:
                msgqlen = len(messages) 
                self.log("stop=%d  len=%d" % (stop, msgqlen), 3)

                if stop == msgqlen:
                    self.log("waiting for messages", 3)
                    # wait for trigger event so we're not constantly polling
                    self._msg_events[CMD_CAN_RECV].wait(1)
                    self._msg_events[CMD_CAN_RECV].clear()
                    self.log("received 'new messages' event trigger", 3)

                # we've gained some messages since last check...
                stop = len(messages)
                continue    # to the big message loop.

            # now actually handle messages
            # here's where we get J1939 specific...
            print messages[idx]
            ts, arbtup, data = messages[idx]
            #datatup = self._splitCanMsg(msg)

            # make ts an offset instead of the real time.
            ts -= startts

            #if arbids != None and arbid not in arbids:
            #    # allow filtering of arbids
            #    idx += 1
            #    continue

            yield((idx, ts, arbtup, data))
            idx += 1


    def J1939recv(self, pf, ps, sa, msgcount=1, timeout=1, start_msg=None, update_last_recv=True):
        out = []

        if start_msg == None:
            start_msg = self._last_recv_idx

        #for msg in self.filterCanMsgs(start_msg=start_msg, advfilters=advfilters, tail=True, maxsecs=timeout):
            #(idx, ts, arbid, data) = msg
            #out.append(msg)
            #self._last_recv_idx = msg[0]
        # FIXME: add in the wait/set interaction for lower perf impact.
        startts = time.time()
        cur = start_msg
        mque = self._messages[J1939MSGS]
        while time.time() < (startts + timeout):
            if cur >= len(mque):
                time.sleep(.001)
                continue

            ts, arbtup, msg = mque[cur]
            cur += 1
           
            # we have a message now, does the PGN match?
            mprio, medp, mdp, mpf, mps, msa = arbtup
            if mpf != pf or mps != ps or msa != sa:
                continue

            # it's passed the checks... add it to the queue
            out.append((ts, arbtup, msg))

            if len(out) >= msgcount:
                break


        # if we actually found something, and we wanted to update last recvd...
        if len(out) and update_last_recv:
            self._last_recv_idx = cur

        return out
    def J1939recv_loose(self, pf=(), ps=None, sa=None, msgcount=1, timeout=1, start_msg=None, update_last_recv=True):
        out = []

        if start_msg == None:
            start_msg = self._last_recv_idx

        #for msg in self.filterCanMsgs(start_msg=start_msg, advfilters=advfilters, tail=True, maxsecs=timeout):
            #(idx, ts, arbid, data) = msg
            #out.append(msg)
            #self._last_recv_idx = msg[0]
        # FIXME: add in the wait/set interaction for lower perf impact.
        startts = time.time()
        cur = start_msg
        mque = self._messages[J1939MSGS]
        while time.time() < (startts + timeout):
            if cur >= len(mque):
                time.sleep(.001)
                continue

            ts, arbtup, msg = mque[cur]
            cur += 1
           
            # we have a message now, does the PGN match? (loose matching)
            mprio, medp, mdp, mpf, mps, msa = arbtup
            if pf is not None:
                if type(pf) in (tuple, list):
                    if mpf not in pf:
                        continue
                else:
                    if mpf != pf:
                        continue

            if ps is not None:
                if type(ps) in (tuple, list):
                    if mps not in ps:
                        continue
                else:
                    if mps != ps:
                        continue

            if sa is not None:
                if type(sa) in (tuple, list):
                    if msa not in sa:
                        continue
                else:
                    if msa != sa:
                        continue

            # it's passed the checks... add it to the queue
            out.append((ts, arbtup, msg))

            if len(out) >= msgcount:
                break


        # if we actually found something, and we wanted to update last recvd...
        if len(out) and update_last_recv:
            self._last_recv_idx = cur

        return out

    def J1939xmit_recv(self, pf, ps, sa, data, recv_count=1, prio=6, edp=0, dp=0, timeout=1, expected_pf=None):
        msgidx = self.getCanMsgCount()
        # FIXME: filter on the expected response PGN
        if expected_pf is None:
            expected_pf = pf

        res = self.J1939xmit(pf, ps, sa, data, prio, edp, dp)
        res = self.J1939recv(expected_pf, sa, ps, recv_count, timeout, start_msg=msgidx)

        return res


    def J1939_Request(self, rpf, rda_ge=0, redp=0, rdp=0, da=0xff, sa=0xfe, prio=0x6, recv_count=255, timeout=2, expected_pf=None):
        pgnbytes = [rda_ge, rpf, redp<<1 | rdp]
        data = ''.join([chr(x) for x in pgnbytes])
        data += '\xff' * (8-len(data))

        if expected_pf is None:
            expected_pf = rpf

        self.J1939xmit(PF_RQST, da, sa, data)
        msgs = self.J1939recv_loose(pf=expected_pf, msgcount=10, timeout=timeout)
        return msgs

    def J1939_ClaimAddress(self, addr, name=0x4040404040404040, prio=6):
        data = struct.pack(">Q", name)
        out = self.J1939xmit_recv(pf=PF_ADDRCLAIM, ps=0xff, sa=addr, data=data, recv_count=10, prio=prio<<2, timeout=2, expected_pf=0xee)
        self.addID(addr)
        return out

    def J1939_ArpAddresses(self):
        '''
        Sends a request for all used addresses... not fully tested
        '''
        #idx = self.getCanMsgCount()
        msgs = self.J1939_Request(PF_ADDRCLAIM, recv_count=255, timeout=3)

        '''
        # FIXME: these are way too loose, for discovery only. tighten down.
        recv_filters = [
                'pf < 0xf0',
                #'pf == 0xee',
                ]

        msgs = self.J1939recv(msgcount=200, timeout=3, advfilters=recv_filters, start_msg=idx)
        '''
        for msg in msgs:
            try:
                msgrepr = self._reprCanMsg(*msg)
                if msgrepr != cancat.DONT_PRINT_THIS_MESSAGE:
                    print msgrepr
            except Exception, e:
                print e
        '''
        example (from start of ECU):
        00000000 1545142410.990 pri/edp/dp: 6/0/0, PG: ea ff  Source: fe  Len: 03, Data: 00ee00              Request
        00000001 1545142411.077 pri/edp/dp: 6/0/0, PG: ee ff  Source: 00  Len: 08, Data: 4cca4d0100000000    Address Claim: id: 0xdca4c mfg: Cummins Inc (formerly Cummins Engine Co) Columbus, IN USA
    
        currently ours:
        00001903 1545142785.127 pri/edp/dp: 6/0/0, PG: ea ff  Source: fe  Len: 03, Data: 00ee00              Request

        '''


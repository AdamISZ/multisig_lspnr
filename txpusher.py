import random, re, errno, os, struct, hashlib, ast
import sys, time, json, types, string, exceptions 

import socket

DEFAULT_SERVERS = {
    'electrum.coinwallet.me': {'h': '8081', 's': '50002', 't': '50001', 'g': '8082'},
    'electrum.hachre.de': {'h': '8081', 's': '50002', 't': '50001', 'g': '8082'},
    'electrum.novit.ro': {'h': '8081', 's': '50002', 't': '50001', 'g': '8082'},
    'electrum.stepkrav.pw': {'h': '8081', 's': '50002', 't': '50001', 'g': '8082'},
    #'ecdsa.org': {'h': '8081', 's': '50002', 't': '50001', 'g': '8082'},
    'electrum.no-ip.org': {'h': '80', 's': '50002', 't': '50001', 'g': '443'},
    'electrum.drollette.com': {'h': '5000', 's': '50002', 't': '50001', 'g': '8082'},
    'btc.it-zone.org': {'h': '80', 's': '110', 't': '50001', 'g': '443'},
    'btc.medoix.com': {'h': '8081', 's': '50002', 't': '50001', 'g': '8082'},
    'spv.nybex.com': {'h': '8081', 's': '50002', 't': '50001', 'g': '8082'},
    'electrum.pdmc.net': {'h': '8081', 's': '50002', 't': '50001', 'g': '8082'},
    'electrum.be': {'h': '8081', 's': '50002', 't': '50001', 'g': '8082'}
}

is_connected = False
#socket
s=None
is_connected=False

    
def connect_electrum():
    global s
    global is_connected
    if is_connected:
        return True
    
    for i in range(1,11):
        serveritem = random.choice(list(DEFAULT_SERVERS.keys()))#list for Py3 compat.
        host = serveritem
        port = DEFAULT_SERVERS[host]['t'] #t=tcp to avoid cert. issues with ssl
        
        #TCP socket setup
        s = socket.socket( socket.AF_INET, socket.SOCK_STREAM )
        s.settimeout(3)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

        try:
            s.connect(( host.encode('ascii'), int(port)))
        except:
            print "failed to connect to:", host, str(port)
            continue #try the next server

        s.settimeout(15)
        is_connected = True
        print "connected to", host, str(port)
        return True
    return False
    
def send_tx(raw_tx):
    global s
    global is_connected
    if not connect_electrum():
        print "error, failed to connect to ANY electrum server"
        socketstop()
        return False
    return send_tcp([('blockchain.transaction.broadcast', [str(raw_tx)])])

        
def get_from_electrum(inputs,t='a'):
    global s
    global is_connected
        
    if not connect_electrum():
        print "Failed to connect to ANY electrum server"
    
    if t=='a':
        req = 'blockchain.address.get_history'
    elif t=='t':
        req = 'blockchain.transaction.get'
    else:
        print "invalid request type to electrum server"
        exit(1)
    tcp_requests = []
    reqreturns=[]
    
    for input in inputs:
        if isinstance(input,list):
            tcp_request = req,input
        else:
            tcp_request= req,[str(input)]
    
        if not send_tcp([tcp_request]):
            print "Failed to send request to electrum server"
        
        out = ''
        
        while is_connected:
            try: 
                timeout = False
                msg = s.recv(1024)
                
            except socket.timeout:
                timeout = True

            except socket.error, err:
                if err.errno in [11, 10035]:
                    print "socket errno", err.errno
                    time.sleep(0.1)
                    continue
                else:
                    print "socket err: ", err.errno
                    raise

            if timeout:
                # ping the server with server.version, as a real ping does not exist yet
                # not sure about this, don't want to get involved in some non-standard weird ping
                print "getting a timeout here"
                time.sleep(0.1)
                continue

            out += msg
            
            if msg == '': 
                print "msg is null"
                is_connected = False
                return
            if out.find('\n') != -1: #means this is end of message, so break out of both loops at end
                while True:
                    x = out.find('\n')
                    if x==-1: 
                        break
                    c = out[0:x]
                    out = out[x+1:]
                    #ast.literal_eval is the best way to read this json stuff into python
                    #don't ask me why json.loads() doesn't work, but right now it doesn't
                    reqreturns.append(ast.literal_eval(c))
                break
                   
    return reqreturns                
                    
def send_tcp(messages):
    global s
    out = ''
    message_id=1
    
    for m in messages:
        method, params = m 
        request = json.dumps( { 'id':message_id, 'method':method, 'params':params } )
        print "-->", request
        message_id += 1
        out += request + '\n'
        while out:
            try:
                sent = s.send(out)
                out = out[sent:]
            except socket.error,e:
                if e[0] in (errno.EWOULDBLOCK,errno.EAGAIN):
                    print_error( "EAGAIN: retrying")
                    time.sleep(0.1)
                    continue
                else:
                    # this happens when we get disconnected
                    print "Not connected, cannot send"
                    socketstop()
                    return False
    
    return True



def socketstop():
    global is_connected
    global s
    if is_connected and s:
        s.shutdown(socket.SHUT_RDWR)
        s.close()


#=====================================================
class EnumException(exceptions.Exception):
    pass

class Enumeration:
    def __init__(self, name, enumList):
        self.__doc__ = name
        lookup = { }
        reverseLookup = { }
        i = 0
        uniqueNames = [ ]
        uniqueValues = [ ]
        for x in enumList:
            if type(x) == types.TupleType:
                x, i = x
            if type(x) != types.StringType:
                raise EnumException, "enum name is not a string: " + x
            if type(i) != types.IntType:
                raise EnumException, "enum value is not an integer: " + i
            if x in uniqueNames:
                raise EnumException, "enum name is not unique: " + x
            if i in uniqueValues:
                raise EnumException, "enum value is not unique for " + x
            uniqueNames.append(x)
            uniqueValues.append(i)
            lookup[x] = i
            reverseLookup[i] = x
            i = i + 1
        self.lookup = lookup
        self.reverseLookup = reverseLookup
    def __getattr__(self, attr):
        if not self.lookup.has_key(attr):
            raise AttributeError
        return self.lookup[attr]
    def whatis(self, value):
        return self.reverseLookup[value]


opcodes = Enumeration("Opcodes", [
    ("OP_0", 0), ("OP_PUSHDATA1",76), "OP_PUSHDATA2", "OP_PUSHDATA4", "OP_1NEGATE", "OP_RESERVED",
    "OP_1", "OP_2", "OP_3", "OP_4", "OP_5", "OP_6", "OP_7",
    "OP_8", "OP_9", "OP_10", "OP_11", "OP_12", "OP_13", "OP_14", "OP_15", "OP_16",
    "OP_NOP", "OP_VER", "OP_IF", "OP_NOTIF", "OP_VERIF", "OP_VERNOTIF", "OP_ELSE", "OP_ENDIF", "OP_VERIFY",
    "OP_RETURN", "OP_TOALTSTACK", "OP_FROMALTSTACK", "OP_2DROP", "OP_2DUP", "OP_3DUP", "OP_2OVER", "OP_2ROT", "OP_2SWAP",
    "OP_IFDUP", "OP_DEPTH", "OP_DROP", "OP_DUP", "OP_NIP", "OP_OVER", "OP_PICK", "OP_ROLL", "OP_ROT",
    "OP_SWAP", "OP_TUCK", "OP_CAT", "OP_SUBSTR", "OP_LEFT", "OP_RIGHT", "OP_SIZE", "OP_INVERT", "OP_AND",
    "OP_OR", "OP_XOR", "OP_EQUAL", "OP_EQUALVERIFY", "OP_RESERVED1", "OP_RESERVED2", "OP_1ADD", "OP_1SUB", "OP_2MUL",
    "OP_2DIV", "OP_NEGATE", "OP_ABS", "OP_NOT", "OP_0NOTEQUAL", "OP_ADD", "OP_SUB", "OP_MUL", "OP_DIV",
    "OP_MOD", "OP_LSHIFT", "OP_RSHIFT", "OP_BOOLAND", "OP_BOOLOR",
    "OP_NUMEQUAL", "OP_NUMEQUALVERIFY", "OP_NUMNOTEQUAL", "OP_LESSTHAN",
    "OP_GREATERTHAN", "OP_LESSTHANOREQUAL", "OP_GREATERTHANOREQUAL", "OP_MIN", "OP_MAX",
    "OP_WITHIN", "OP_RIPEMD160", "OP_SHA1", "OP_SHA256", "OP_HASH160",
    "OP_HASH256", "OP_CODESEPARATOR", "OP_CHECKSIG", "OP_CHECKSIGVERIFY", "OP_CHECKMULTISIG",
    "OP_CHECKMULTISIGVERIFY",
    ("OP_SINGLEBYTE_END", 0xF0),
    ("OP_DOUBLEBYTE_BEGIN", 0xF000),
    "OP_PUBKEY", "OP_PUBKEYHASH",
    ("OP_INVALIDOPCODE", 0xFFFF),
])

__b58chars = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
__b58base = len(__b58chars)

def b58encode(v):
    """ encode v, which is a string of bytes, to base58."""

    long_value = 0L
    for (i, c) in enumerate(v[::-1]):
        long_value += (256**i) * ord(c)

    result = ''
    while long_value >= __b58base:
        div, mod = divmod(long_value, __b58base)
        result = __b58chars[mod] + result
        long_value = div
    result = __b58chars[long_value] + result

    # Bitcoin does a little leading-zero-compression:
    # leading 0-bytes in the input become leading-1s
    nPad = 0
    for c in v:
        if c == '\0': nPad += 1
        else: break

    return (__b58chars[0]*nPad) + result

def hash_160_to_bc_address(h160, addrtype = 0):
    vh160 = chr(addrtype) + h160
    h = hashlib.sha256(hashlib.sha256(vh160).digest()).digest()
    addr = vh160 + h[0:4]
    return b58encode(addr)
    
def match_decoded(decoded, to_match):
    if len(decoded) != len(to_match):
        return False;
    for i in range(len(decoded)):
        if to_match[i] == opcodes.OP_PUSHDATA4 and decoded[i][0] <= opcodes.OP_PUSHDATA4 and decoded[i][0]>0:
            continue  # Opcodes below OP_PUSHDATA4 all just push data onto stack, and are equivalent.
        if to_match[i] != decoded[i][0]:
            return False
    return True

def get_address_from_output_script(bytes):
    decoded = [ x for x in script_GetOp(bytes) ]

    # The Genesis Block, self-payments, and pay-by-IP-address payments look like:
    # 65 BYTES:... CHECKSIG
    '''match = [ opcodes.OP_PUSHDATA4, opcodes.OP_CHECKSIG ]
    if match_decoded(decoded, match):
        return True, public_key_to_bc_address(decoded[0][1])
    '''
    
    # Pay-by-Bitcoin-address TxOuts look like:
    # DUP HASH160 20 BYTES:... EQUALVERIFY CHECKSIG
    match = [ opcodes.OP_DUP, opcodes.OP_HASH160, opcodes.OP_PUSHDATA4, opcodes.OP_EQUALVERIFY, opcodes.OP_CHECKSIG ]
    if match_decoded(decoded, match):
        return False, hash_160_to_bc_address(decoded[2][1])

    # p2sh
    match = [ opcodes.OP_HASH160, opcodes.OP_PUSHDATA4, opcodes.OP_EQUAL ]
    if match_decoded(decoded, match):
        return False, hash_160_to_bc_address(decoded[1][1],5)

    return False, "(None)"

def script_GetOp(bytes):
    i = 0
    while i < len(bytes):
        vch = None
        opcode = ord(bytes[i])
        i += 1
        if opcode >= opcodes.OP_SINGLEBYTE_END:
            opcode <<= 8
            opcode |= ord(bytes[i])
            i += 1

        if opcode <= opcodes.OP_PUSHDATA4:
            nSize = opcode
            if opcode == opcodes.OP_PUSHDATA1:
                nSize = ord(bytes[i])
                i += 1
            elif opcode == opcodes.OP_PUSHDATA2:
                (nSize,) = struct.unpack_from('<H', bytes, i)
                i += 2
            elif opcode == opcodes.OP_PUSHDATA4:
                (nSize,) = struct.unpack_from('<I', bytes, i)
                i += 4
            vch = bytes[i:i+nSize]
            i += nSize

        yield (opcode, vch, i)

def get_address_from_input_script(bytes):
    try:
        decoded = [ x for x in script_GetOp(bytes) ]
    except:
        # coinbase transactions raise an exception
        print "cannot find address in input script", bytes.encode('hex')
        return [], [], "(None)"

    # payto_pubkey
    match = [ opcodes.OP_PUSHDATA4 ]
    if match_decoded(decoded, match):
        return None, None, "(pubkey)"
    
    # non-generated TxIn transactions push a signature
    # (seventy-something bytes) and then their public key
    # (65 bytes) onto the stack:
    match = [ opcodes.OP_PUSHDATA4, opcodes.OP_PUSHDATA4 ]
    if match_decoded(decoded, match):
        return None, None, public_key_to_bc_address(decoded[1][1])
        
    # p2sh transaction, 2 of n
    match = [ opcodes.OP_0 ]
    while len(match) < len(decoded):
        match.append(opcodes.OP_PUSHDATA4)

    if match_decoded(decoded, match):

        redeemScript = decoded[-1][1]
        num = len(match) - 2
        signatures = map(lambda x:x[1][:-1].encode('hex'), decoded[1:-1])

        dec2 = [ x for x in script_GetOp(redeemScript) ]

        # 2 of 2
        match2 = [ opcodes.OP_2, opcodes.OP_PUSHDATA4, opcodes.OP_PUSHDATA4, opcodes.OP_2, opcodes.OP_CHECKMULTISIG ]
        if match_decoded(dec2, match2):
            pubkeys = [ dec2[1][1].encode('hex'), dec2[2][1].encode('hex') ]
            return pubkeys, signatures, hash_160_to_bc_address(hash_160(redeemScript), 5)
 
        # 2 of 3
        match2 = [ opcodes.OP_2, opcodes.OP_PUSHDATA4, opcodes.OP_PUSHDATA4, opcodes.OP_PUSHDATA4, opcodes.OP_3, opcodes.OP_CHECKMULTISIG ]
        if match_decoded(dec2, match2):
            pubkeys = [ dec2[1][1].encode('hex'), dec2[2][1].encode('hex'), dec2[3][1].encode('hex') ]
            return pubkeys, signatures, hash_160_to_bc_address(hash_160(redeemScript), 5)

    print "cannot find address in input script", bytes.encode('hex')
    return [], [], "(None)"

def hash_160(public_key):
    try:
        md = hashlib.new('ripemd160')
        md.update(hashlib.sha256(public_key).digest())
        return md.digest()
    except:
        import ripemd
        md = ripemd.new(hashlib.sha256(public_key).digest())
        return md.digest()


def public_key_to_bc_address(public_key):
    h160 = hash_160(public_key)
    return hash_160_to_bc_address(h160)


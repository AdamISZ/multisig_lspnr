import random, os, json, sys, ast, time
from pybitcointools import *
import txpusher

#this should be defined in a config - MultsigStorageDirectory
msd = '/root/pybitcointools/multisig_store'

#This should be set in set_escrow_pubkey before doing anything
escrow_pubkey='04796ea7f5ca5afa6f3ba907a51484b8d5959a69f38551444538e72280f8dcb1760c0b69ed714fb835ca4bc89fe04132d175dace5004d679c6a85b69078b798495'


def set_escrow_pubkey(pubkey):
    global escrow_pubkey
    escrow_pubkey = pubkey
    
#txid is the unique transaction identifier allowing the user to correlate
#his keys with the transaction
def create_tmp_address_and_store_keypair(txid):
    #no brainwalleting; not safe (but RNG should be considered)
    priv = sha256(str(random.randrange(2**256)))
    pub = privtopub(priv)
    addr = pubtoaddr(pub)
    #write data to file
    with open(os.path.join(msd,txid+'.private'),'wb') as f:
        f.write('DO NOT LOSE, ALTER OR SHARE THIS FILE - WITHOUT THIS FILE, YOUR MONEY IS AT RISK. BACK UP! YOU HAVE BEEN WARNED!\r\n')
        f.write(addr+'\r\n')
        f.write(pub+'\r\n')
        f.write(priv+'\r\n')
        
    #access to data at runtime for convenience
    return (addr,pub,priv)

#called by buyer AND seller
def create_file_for_sending_to_counterparty_to_prepare_multisig(txid):
    #to pass the public key to the counterparty allowing for multisig address
    #and script creation
        
    #to avoid a terrible error, include the escrow pubkey in the message
    #for verification:
    global escrow_pubkey
    check_escrow_present()
    
    #read the pub key from the .private file
    with open(os.path.join(msd,txid+'.private'),'r') as f:
        f.readline()
        f.readline()
        pub = f.readline() #TODO : error checking is critical here
    with open(os.path.join(msd,txid+'.share'),'wb') as f:
        f.write("THIS FILE IS SAFE TO SHARE WITH OTHERS. SEND IT TO YOUR COUNTERPARTY TO ALLOW THEM TO DO ESCROW WITH YOU.\r\n")
        f.write(escrow_pubkey+'\r\n')
        f.write(pub+'\r\n')
        
    return True

#when user has received pubkey from counterparty, can set up the multisig address
#payment INTO the multisig address, by seller, happens outside the application
def create_multisig_address(pubfile1,pubfile2):
    global escrow_pubkey
    check_escrow_present()
    pubs = [escrow_pubkey]
    for f in [pubfile1,pubfile2]:
        with open(f,'r') as fi:
            fi.readline()
            fi.readline()
            pubs.append(fi.readline().strip())
    mscript = mk_multisig_script(pubs,2,3)
    msigaddr = scriptaddr(mscript.decode('hex'))
    return (msigaddr,mscript)

#can be used by a counterparty to check whether money has been paid in
def check_balance_at_multisig(pubfile1,pubfile2):
    msigaddr, mscript = create_multisig_address(pubfile1,pubfile2)
    confirmed, unconfirmed = get_balance_lspnr(msigaddr)
    return "Balance at",msigaddr,"is: confirmed:",confirmed,"unconfirmed:", unconfirmed

#called by both counterparties (and can be escrow) to generate a signature to apply
def create_sig_for_redemption(txid,pubfile1,pubfile2,amt,txfee,addr_to_be_paid,privfile=None):
    msigaddr,mscript = create_multisig_address(pubfile1,pubfile2)
    amt = int(amt*1e8)
    txfee = int(txfee*1e8)
    outs = [{'value':amt-txfee,'address':addr_to_be_paid}]
    ins = history(msigaddr)[0]
    tmptx = mktx(history(msigaddr),outs)
    if not privfile:
        privfile = os.path.join(msd,txid+'.private')
    with open(privfile,'r') as f:
        f.readline() #todo - how to do 3 at once?
        f.readline()
        f.readline()
        priv = f.readline().strip()
    sig =  multisign(tmptx.decode('hex'),0,mscript.decode('hex'),priv)
    #now store the signature in a file
    with open(os.path.join(msd,txid+'.sig'),'wb') as f:
        f.write(sig+'\r\n')
    #for convenience
    return sig

#any party in possession of two signatures can call this to broadcast
#the tx to the network
def sign_and_broadcast_to_network(txid,sigfile1,sigfile2,pubfile1,pubfile2,amt,txfee,addr_to_be_paid):
    sigs=[]
    for f in [sigfile1,sigfile2]:
        with open(f,'r') as fi:
            sigs.append(fi.readline().strip())
        
    with open(os.path.join(msd,txid+'.private'),'r') as f:
        for i in range(1,4): f.readline()
        priv = f.readline()
    msigaddr, mscript = create_multisig_address(pubfile1,pubfile2)
    amt = int(amt*1e8)
    txfee = int(txfee*1e8)
    outs = [{'value':amt-txfee,'address':addr_to_be_paid}]
    ins = history(msigaddr)[0]
    tmptx = mktx(history(msigaddr),outs)
    finaltx = apply_multisignatures(tmptx,0,mscript,sigs)
    txpusher.send_tx(finaltx)
    return tx_hash(finaltx).encode('hex')


def check_escrow_present():
    global escrow_pubkey
    if not escrow_pubkey:
        raise Exception("The escrow's pubkey should be set before depositing escrowed bitcoins!")
        

                                                
#will accurately report the current confirmed and unconfirmed balance
#in the given address, and return (confirmed, unconfirmed).
#CONDITIONS: will give up if :
# *address has more than one unconfirmed transaction - this is quite possible,
# but most wallets won't spend unconfirmed coins, so we can assume normal
# users won't do this - I hope.
# *address has more than 2 transactions in the same block at any time in the past
# (this is rare)
#If the number of past transactions at the address is very large (>100), this
#function will take a LONG time - it is not fit for checking Satoshi Dice adds!
#Running time for normal addresses will usually be subsecond, but fairly
#commonly will take 5-20 seconds due to Electrum server timeouts.
def get_balance_lspnr(addr_to_test):
    
    received_btc = 0.0
    #query electrum for a list of txs at this address
    txdetails = txpusher.get_from_electrum([addr_to_test],t='a')
    x = txdetails[0]
    print x
    #need to build a list of requests to send on to electrum, asking it for
    #the raw transaction data
    args=[]
    unconfirmedtxhash = None
    if not x['result']:
        return (0.0,0.0)
    for txdict in x['result']:
        if txdict["height"]==0:
            #unconfirmeds show up as block height 0
            #note: more than 1 unconfirmed is quite normal in general activity, 
            #but basically inconceivable in our multisig use case; therefore,
            #and bearing in mind the difficulty of establishing time order in this
            #special case, we will assume no more than one.
            if unconfirmedtxhash: 
                raise Exception("Unexpectedly found more than one unconfirmed\
                                 transaction for this address.")
            unconfirmedtxhash = txdict["tx_hash"]
        args.append([txdict["tx_hash"],txdict["height"]])
        
    #place transactions in order of height for correct calculation of balance
    args.sort(key=lambda x: int(x[1]))

    #in case two transactions are at the same block height, we need to reorder 
    #based on input/output relationship. First create a dict of tx hashes,
    #keyed by blockheight, to look for 2 txs with same block height
    heightsdict = {}
    for arg in args:
        if arg[1] in heightsdict.keys():
            heightsdict[arg[1]].append(arg[0])
        else:
            heightsdict[arg[1]]=[arg[0]]
        
    for k,v in heightsdict.iteritems():
        outpoints1=[]
        outpoints2=[]
        if len(v)==2:
            for i,arg in enumerate(args):
                    if v[0] == arg[0]:
                        pos1 = i
                    if v[1]==arg[0]:
                        pos2 = i
            raw1,raw2 = txpusher.get_from_electrum([args[pos1],args[pos2]],t='t')
            tx1 = deserialize(raw1['result'])
            tx2 = deserialize(raw2['result'])
            txh1 = tx_hash(raw1['result']).encode('hex')
            txh2 = tx_hash(raw2['result']).encode('hex')
            for input in tx1['ins']:
                outpoints1.append(input['outpoint']['hash'])
            for input in tx2['ins']:
                outpoints2.append(input['outpoint']['hash'])
            if txh2 in outpoints1:
                #swap 1 and 2 in args
                args[pos1:pos1+2]=reversed(args[pos1:pos1+2])
        elif len(v)>2:
            #too much additional complexity, abandoned for now
            raise Exception("Too many transactions in one block, giving up")
            break

    #unconfirmed have been sorted to the start, but should be at the end:
    if args[0][1]==0:
        unconfirmed_arg = args[0]
        args= args[1:]
        args.append(unconfirmed_arg)
        
    #we finally have a correctly ordered list of transactions to process;        
    x= txpusher.get_from_electrum(args,t='t')

    uncon_input=False
    uncon_output = 0.0
    unconfirmed_spends = 0.0
    
    #a dictionary of bitcoin amounts received, indexed by transaction hash:
    prev_outs={}

    for y in x:
        uncon=False
        rawtx = y['result']
        tx = deserialize(rawtx)
        txh = tx_hash(rawtx).encode('hex')
        if txh == unconfirmedtxhash: uncon=True
        
        for input in tx['ins']:
            pubkeys,signatures, addr = \
            txpusher.get_address_from_input_script(input['script'].decode('hex'))
    
            if not addr == addr_to_test: continue
            
            #we need to find which previous output is being spent - it must exist.
            try:
                bitcoins_being_spent = prev_outs[input['outpoint']['hash']]
            except:
                raise Exception("failed to find the reference to which\
                                 output's being spent!")
                
            if not uncon:
                received_btc -= bitcoins_being_spent 
                print "after spending, balance set to:", received_btc
            else: 
                unconfirmed_spends += bitcoins_being_spent
            
        for output in tx['outs']:
            ispubkey,addr = \
            txpusher.get_address_from_output_script(output['script'].decode('hex'))
            
            if not addr == addr_to_test: continue
            
            bitcoins =  output['value'] * 0.00000001
            
            if not uncon:
                received_btc +=bitcoins
                prev_outs[txh]=bitcoins
                
            else: 
                uncon_output = output['value'] * 0.00000001
            
    print "Final confirmed balance: ", received_btc
    #add unconfirmed balance changes last, and always input before output
    conf_bal = received_btc
    
    received_btc += uncon_output
    received_btc -= unconfirmed_spends
    print "Final balance, including unconfirmed:", received_btc
    unconf_bal = received_btc
    
    return conf_bal,unconf_bal

if __name__ == "__main__":
    
    #Test 1: make and store a local "ephemeral" address and keypair
    #for signing a multisig
    '''addr, pub, priv = create_tmp_address_and_store_keypair('123')
    print addr, pub, priv
    '''
    
    #Test 2: make share-able file to give to counterparty to set up
    #the multisig
    '''
    create_file_for_sending_to_counterparty_to_prepare_multisig('123')
    '''
    
    #Test 3: generate the multisig; after this, pay into the address (seller)
    '''print create_multisig_address('/root/pybitcointools/multisig_store/123.share',\
                                  '/root/pybitcointools/multisig_store/my123.share')
    '''
    
    #Test 4: check whether it's been paid into the multisig address
    '''
    print check_balance_at_multisig('/root/pybitcointools/multisig_store/123.share',\
                                  '/root/pybitcointools/multisig_store/my123.share')
    '''
    
    #Test 5: sign the transaction and store it in a file to send on 
    '''
    create_sig_for_redemption('123','/root/pybitcointools/multisig_store/123.share',\
                                  '/root/pybitcointools/multisig_store/my123.share',\
                                    .001,0.0002,'1iHCdVZrW8yLKunsg7y2kssN1dCqM4m52')
    '''
    
    #Test 6: other party also signs
    '''
    create_sig_for_redemption('123','/root/pybitcointools/multisig_store/123.share',\
                                  '/root/pybitcointools/multisig_store/my123.share',\
                                    .001,0.0002,'1iHCdVZrW8yLKunsg7y2kssN1dCqM4m52',\
                                    '/root/pybitcointools/multisig_store/my123.private')
    '''
    
    #Test 7: broadcast the transaction
    '''
    print sign_and_broadcast_to_network('123',\
        '/root/pybitcointools/multisig_store/my123.sig',\
        '/root/pybitcointools/multisig_store/123.sig',\
        '/root/pybitcointools/multisig_store/123.share',\
        '/root/pybitcointools/multisig_store/my123.share',\
        0.001,0.0002,'1iHCdVZrW8yLKunsg7y2kssN1dCqM4m52')
    '''
    
    
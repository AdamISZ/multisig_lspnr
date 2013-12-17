import random, os, json, sys, ast, time
from pybitcointools import *
import electrumaccessor as ea

#this should be defined in a config - MultsigStorageDirectory
msd = 'C:/lsnpr/paysty-eu/ssllog-master/multisig_store'

#This should be set in set_escrow_pubkey before doing anything
escrow_pubkey='045e1a2a55ccf714e72b9ca51b89979575aad326ba21e15702bbf4e1000279dc72208abd3477921064323b0254c9ead6367ebce17da3ad6037f7a823d65e957b20'


def set_escrow_pubkey(pubkey):
    global escrow_pubkey
    escrow_pubkey = pubkey
    
#uniqueid is the unique transaction identifier allowing the user to correlate
#his keys with the transaction; calling modules are tasked with constructing it
def create_tmp_address_and_store_keypair(uniqueid):
    #no brainwalleting; not safe (but RNG should be considered)
    priv = sha256(str(random.randrange(2**256)))
    pub = privtopub(priv)
    addr = pubtoaddr(pub)
    #write data to file
    with open(os.path.join(msd,uniqueid+'.private'),'wb') as f:
        f.write('DO NOT LOSE, ALTER OR SHARE THIS FILE - WITHOUT THIS FILE, YOUR MONEY IS AT RISK. BACK UP! YOU HAVE BEEN WARNED!\r\n')
        f.write(addr+'\r\n')
        f.write(pub+'\r\n')
        f.write(priv+'\r\n')
    
    global escrow_pubkey
    check_escrow_present()
    with open(os.path.join(msd,uniqueid+'.private'),'r') as f:
        f.readline()
        f.readline()
        pub = f.readline() #TODO : error checking is critical here
    store_share(pub,uniqueid)
    #access to data at runtime for convenience
    return (addr,pub,priv)

def store_share(pubkey,uniqueid):
    global escrow_pubkey
    check_escrow_present()
    with open(os.path.join(msd,uniqueid+'.share'),'wb') as f:
        f.write("THIS FILE IS SAFE TO SHARE WITH OTHERS. SEND IT TO YOUR COUNTERPARTY TO ALLOW THEM TO DO ESCROW WITH YOU.\r\n")
        f.write(escrow_pubkey+'\r\n')
        f.write(pubkey+'\r\n')
    
#when user has received pubkey from counterparty, can set up the multisig address
#payment INTO the multisig address, by seller, happens outside the application
#uniqueid1 is YOU, 2 is counterparty, in case this is called from web app
def create_multisig_address(uniqueid1,uniqueid2):
    pubs = get_ordered_pubkeys(uniqueid1, uniqueid2)
    if not pubs:
        return ('','')
    mscript = mk_multisig_script(pubs,2,3)
    msigaddr = scriptaddr(mscript.decode('hex'))
    return (msigaddr,mscript)

def get_ordered_pubkeys(uniqueid1,uniqueid2):
    global escrow_pubkey
    check_escrow_present()
    pubs = [escrow_pubkey]
    try:
        for f in [os.path.join(msd,uniqueid1+'.share'),os.path.join(msd,uniqueid2+'.share')]:
            with open(f,'r') as fi:
                fi.readline()
                fi.readline()
                pubs.append(fi.readline().strip())
    except:
        return None
    #necessary for ensuring unique result for address
    pubs.sort()
    return pubs

#can be used by a counterparty to check whether money has been paid in
def check_balance_at_multisig(uniqueid1,uniqueid2,addr=''):
    if not addr:
        msigaddr, mscript = create_multisig_address(uniqueid1,uniqueid2)
    else:
        msigaddr = addr
    return get_balance_lspnr(msigaddr)
    
#called by both counterparties (and can be escrow) to generate a signature to apply
#will fail and return None if the multisig address has not been funded
def create_sig_for_redemption(uniqueid,uniqueid1,uniqueid2,amt,txfee,addr_to_be_paid):
    msigaddr,mscript = create_multisig_address(uniqueid1,uniqueid2)
    amt = int(amt*1e8)
    txfee = int(txfee*1e8)
    outs = [{'value':amt-txfee,'address':addr_to_be_paid}]
    if len(history(msigaddr))<1:
        print "sorry, the multisig address:",msigaddr,"doesn't seem to have any transactions yet. Wait until \'python multisig.py multi_check\' shows CONFIRMED balance."
        return None
    ins = history(msigaddr)[0]
    tmptx = mktx(history(msigaddr),outs)
    privfile = os.path.join(msd,uniqueid+'.private')
    with open(privfile,'r') as f:
        f.readline() #todo - how to do 3 at once?
        f.readline()
        f.readline()
        priv = f.readline().strip()
    sig =  multisign(tmptx.decode('hex'),0,mscript.decode('hex'),priv)
    #now store the signature in a file
    with open(os.path.join(msd,uniqueid+'.sig'),'wb') as f:
        f.write(sig+'\r\n')
    #for convenience
    return sig

#we assume: exactly two signatures are applied, which can be any
#of buyer,seller and escrow. If the order in which they are provided is
#different to that used to create the multisig address, swap is needed so
#returns True
def need_swap(uniqueid1,uniqueid2,pubs):
    pos = {}
    for id in [uniqueid1,uniqueid2]:
        with open(os.path.join(msd,id+'.share'),'r') as fi:
            fi.readline()
            fi.readline()
            pub = fi.readline().strip()
            pos[id]=pubs.index(pub)
            
    if pos[uniqueid1]>pos[uniqueid2]:
        return True
    return False

#any party in possession of two signatures can call this to broadcast
#the tx to the network
def broadcast_to_network(sigid1,sigid2,uniqueid1,uniqueid2,amt,txfee,addr_to_be_paid):
    sigs=[]
    for sigid in [sigid1,sigid2]:
        with open(os.path.join(msd,sigid+'.sig'),'r') as fi:
            sigs.append(fi.readline().strip())
    
    #sigfiles have to be applied in the same order as the pubkeys;
    #this is alphanumeric order of pubkeys:
    if need_swap(sigid1,sigid2,get_ordered_pubkeys(uniqueid1,uniqueid2)):
        sigs.reverse()
    
    msigaddr, mscript = create_multisig_address(uniqueid1,uniqueid2)
    amt = int(amt*1e8)
    txfee = int(txfee*1e8)
    outs = [{'value':amt-txfee,'address':addr_to_be_paid}]
    ins = history(msigaddr)[0]
    tmptx = mktx(history(msigaddr),outs)
    finaltx = apply_multisignatures(tmptx,0,mscript,sigs)
    rspns = ea.send_tx(finaltx)
    print "Electrum server sent back:",rspns
    return tx_hash(finaltx).encode('hex')


def check_escrow_present():
    global escrow_pubkey
    if not escrow_pubkey:
        raise Exception("The escrow's pubkey should be set before depositing escrowed bitcoins!")
        

                                                
#will accurately report the current confirmed and unconfirmed balance
#in the given address, and return (confirmed, unconfirmed).
#If the number of past transactions at the address is very large (>100), this
#function will take a LONG time - it is not fit for checking Satoshi Dice adds!
#Running time for normal addresses will usually be subsecond, but fairly
#commonly will take 5-20 seconds due to Electrum server timeouts.
def get_balance_lspnr(addr_to_test):
    
    received_btc = 0.0
    unconf = 0.0
    #query electrum for a list of txs at this address
    txdetails = ea.get_from_electrum([addr_to_test],t='a')
    x = txdetails[0]
    print x
    #need to build a list of requests to send on to electrum, asking it for
    #the raw transaction data
    args=[]
    
    for txdict in x['result']:
        args.append([txdict["tx_hash"],txdict["height"]])
    
    #place transactions in order of height for correct calculation of balance
    args.sort(key=lambda x: int(x[1]))
    #unconfirmed will now be at the beginning but need to be at the end
    unconf_args = [item for item in args if item[1]==0]
    conf_args = [item for item in args if item[1]!=0]
    args = conf_args +unconf_args
    
    txs= ea.get_from_electrum(args,t='t')
    
    #Before counting input and output bitcoins, we must first
    #loop through all transactions to find all previous outs used
    #as inputs; otherwise we would have to correctly establish chronological
    #order, which is impossible if more than one tx is in the same block
    #(in practice it would be possible given some arbitrary limit on the 
    #number of transactions in the same block, but that's messy).
    prev_outs={}
    for y in txs:
        rawtx=y['result']
        tx=deserialize(rawtx)
        txh = tx_hash(rawtx).encode('hex')
        for output in tx['outs']:
            ispubkey,addr = \
            ea.get_address_from_output_script(output['script'].decode('hex'))
            if not addr == addr_to_test: continue
            bitcoins =  output['value'] * 0.00000001
            prev_outs[txh]=bitcoins
    
    for i,y in enumerate(txs):
        rawtx = y['result']
        tx = deserialize(rawtx)
        print tx
        txh = tx_hash(rawtx).encode('hex')
        
        for input in tx['ins']:
            pubkeys,signatures, addr = \
            ea.get_address_from_input_script(input['script'].decode('hex'))
            print "Got this address:", addr
            if not addr == addr_to_test: continue
            
            #we need to find which previous output is being spent - it must exist.
            try:
                bitcoins_being_spent = prev_outs[input['outpoint']['hash']]
            except:
                raise Exception("failed to find the reference to which\
                                 output's being spent!")
            if args[i][1]==0:
                unconf -= bitcoins_being_spent
            received_btc -= bitcoins_being_spent 
            print "after spending, balance set to:", received_btc
            
        for output in tx['outs']:
            ispubkey,addr = \
            ea.get_address_from_output_script(output['script'].decode('hex'))
            print "Got address: ",addr
            if not addr == addr_to_test: continue
            bitcoins =  output['value'] * 0.00000001
            if args[i][1]==0:
                unconf += bitcoins
            received_btc +=bitcoins
            
    print "Final unconfirmed balance: ", received_btc
    print "Final confirmed balance: ", received_btc - unconf
    return received_btc-unconf,received_btc

if __name__ == "__main__":
    
    if not os.path.isdir(msd): os.mkdir(msd)
    
    if len(sys.argv)<2:
        print "Before you start, make sure to write an escrow's public key as a string in escrow_pubkey at the top of this file"
        print "If you have no escrow pubkey, you can pretend to be the escrow yourself and generate a pubkey with the command create, and then store it in this file"
        print "In real usage, the escrow is a third party who will store his own .private and give you a .share file with this pubkey."
        print "Also, the full path of the multisig storage directory should be set in the variable msd"
        print "===================================================================="
        print "To carry out the 2 of 3 escrow process, provide arguments as follows:"
        print "===================================================================="
        print "python multisig.py create unique_id (creates an address used only for signing, a .private file and a .share file)"
        print "python multisig.py multi_create uniqueid1 uniqueid2 (generates the multisig address to be used; will be the same for both counterparties)"
        print "python multisig.py multi_check uniqueid1 uniqueid2 (checks the balance of the new multisig address)"
        print "python multisig.py sign uniqueid_to_sign_with uniqueid1 uniqueid2 amount_incl_txfee txfee addr_to_pay [.private file] (creates a file with suffix .sig containing this party\'s signature to the transaction"
        print "python multisig.py redeem sigid1 sigid2 uniqueid1 uniqueid2 amount_incl_txfee txfee addr_to_pay"
        exit()
        
    if sys.argv[1]=='create': #second argument is transaction id
        addr, pub, priv = create_tmp_address_and_store_keypair(sys.argv[2])
        print "data stored in: ",os.path.join(msd,sys.argv[2]+'.private')
        print "shareable file stored in:",os.path.join(msd,sys.argv[2]+'.share')
    
    elif sys.argv[1]=='multi_create': #2nd and 3rd arguments are .share files
        print "Multisig address:",create_multisig_address(sys.argv[2],sys.argv[3])
        print "If you're the bitcoin SELLER, please pay the appropriate amount into the address now."
        print "If you're the bitcoin BUYER, check whether the appropriate amount has been paid into this address."

    elif sys.argv[1]=='multi_check': #second and third arguments are ...
        check_balance_at_multisig(sys.argv[2],sys.argv[3])
    
    elif sys.argv[1]=='sign': #arguments: ... amount to pay INCLUDING tx fee 6: tx fee 7:address to pay out to
        create_sig_for_redemption(sys.argv[2],sys.argv[3],sys.argv[4],float(sys.argv[5]),\
                                float(sys.argv[6]),sys.argv[7])
        print "Signature file was created in:",os.path.join(msd,sys.argv[2]+'.sig')
    
    elif sys.argv[1]=='redeem':
        #args: redeem  ...amt txfee address_to_pay
        sys.argv[6]=float(sys.argv[6])
        sys.argv[7]=float(sys.argv[7])
        print broadcast_to_network(*sys.argv[2:9])
    
    #for testing balance checking feature directly from an address
    elif sys.argv[1]=='adtest':
        get_balance_lspnr(sys.argv[2])
    
    else:
        print "incorrect first argument to script"
        
    
    
    
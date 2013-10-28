multisig_lspnr
==============

bitcoin escrow with multisignatures, built in Python only and using Electrum servers
to query the network (no Electrum installation needed).
pybitcointools by Vitalik Buterin is used here for signature,transaction,keypair and 
address generation, and is included here as a snapshot 
(d64f3df78497cfa8446389d47f00a21e0a5c7fc5, basically), since it is still in active development.

Instructions
===============
After git cloning or unzipping, go to the root directory and type:

    python multisig.py
    
with no arguments. This should provide the following instructions for command line testing:

Before you start, make sure to write an escrow's public key as a string in escrow_pubkey at the top of this file
If you have no escrow pubkey, you can pretend to be the escrow yourself and generate a pubkey with the command create, and then store it in this file
In real usage, the escrow is a third party who will store his own .private and give you a .share file with this pubkey.
Also, the full path of the multisig storage directory should be set in the variable msd
====================================================================
To carry out the 2 of 3 escrow process, provide arguments as follows:
====================================================================
python multisig.py create txid (creates an address used only for signing)
python multisig.py share txid (creates a file you can share with your counterparty)
python multisig.py multi_create sharefile1 sharefile2 (generates the multisig address to be used; will be the same for both counterparties)
python multisig.py multi_check sharefile1 sharefile2 (checks the balance of the new multisig address)
python multisig.py sign txid sharefile1 sharefile2 amount_incl_txfee txfee addr_to_pay [.private file] (creates a file with suffix .sig containing this party's signature to the transaction
python multisig.py redeem txid sigfile1 sigfile2 sharefile1 sharefile2 amount_incl_txfee txfee addr_to_pay


import os, sys, inspect, struct
from btchip.btchip import *
from btchip.btchipUtils import *
from btchip.bitcoinTransaction import *
from btchip.bitcoinVarint import *
import simplejson as json
import settings, pprint, getpass, binascii, hashlib, sys, re
from signMessage import signMessage
import pycoin.scripts.tx, pycoin.tx, pycoin.tx.pay_to

pp = pprint.PrettyPrinter(indent=2)

def main():
  """This module signs the downloaded JSON files from Coinkite's co-signing page."""

  if len(sys.argv) < 2:
    print "Usage: python signTxCoinkiteJSON.py <JSON path>"
    exit(1)

  # Get path from cli
  inputPath = sys.argv[1]

  f = open(sys.argv[1], 'r')
  signData = json.load(f)
  requestData = json.loads(signData['contents'])

  # Get Dongle
  dongle = getDongle(False) # Bool is debug mode
  app = btchip(dongle)

  # Authenticate with dongle
  pin = getpass.getpass("PIN: ")
  app.verifyPin(pin)

  result = signCoinkiteJSON(app, dongle, requestData)
  body = createReturnJSON(app, dongle, result)

  fName = 'output-' + requestData['request'] + '-' + requestData['cosigner'] + '.json'
  fOut = open(fName, 'w')
  fOut.write(json.dumps(body))
  fOut.close()

  print "Output written to " + fName

def signCoinkiteJSON(app, dongle, requestData, promptTx=True):
  # print json.dumps(requestData, indent=2) # print req data
  result = {}
  result['cosigner'] = requestData['cosigner']
  result['request'] = requestData['request']
  result['signatures'] = []

  if promptTx:
    # Give a nice overview of what's being signed and give the user a chance to bail.
    isTestnet = requestData['xpubkey_display'][0:4] == 'tpub'
    prettyPrintTX(requestData['raw_unsigned_txn'], isTestnet)
    for i in requestData['redeem_scripts']:
      print "Input scripts:"
      prettyPrintRedeemScript(requestData['redeem_scripts'][i]['redeem'], isTestnet)
    print "Please press <enter> to confirm this data is expected, or <ctrl-c> to exit."
    raw_input("")

  # TODO verify change address is controlled by us
  # TODO verify hash we're signing is from this tx

  OUTPUT = bytearray("")
  transaction = bitcoinTransaction(bytearray(requestData['raw_unsigned_txn'].decode('hex')))
  writeVarint(len(transaction.outputs), OUTPUT)
  for troutput in transaction.outputs:
  	OUTPUT.extend(troutput.serialize())

  wallets = {}

  # Sign each input
  for i, signInput in enumerate(requestData['inputs']):
    # Get the input from this transaction
    tx = bytearray(requestData['input_info'][i]['txn'].decode('hex'))
    index = requestData['input_info'][i]['out_num']
    transactionInput = {}
    transactionInput['trustedInput'] = False
    value = tx[::-1]
    value.extend(bytearray(struct.pack('<I', index)))
    transactionInput['value'] = value

    # Start composing transaction
    print "Creating transaction on BTChip..."
    redeemScript = requestData['redeem_scripts'][signInput[0]]['redeem']
    app.startUntrustedTransaction(True, 0, [transactionInput], bytearray(redeemScript.decode('hex')))
    app.finalizeInputFull(OUTPUT)

    # Get pub key for this input
    path = signInput[0]
    keyHash = requestData['req_keys'][path]
    print "Signing..."
    keyPath = settings.KEYPATH_BASE + "/" + path
    pubKeyRaw = app.getWalletPublicKey(keyPath)
    wallets[path] = str(compress_public_key(pubKeyRaw['publicKey'])).encode('hex')
    print "Your pubkey for %s: %s" % (keyPath, wallets[path])
    try:
      assert pubKeyRaw['address'] == keyHash[0]
    except:
      print "ERROR: Attempting to sign with pubkey " + pubKeyRaw['address'] + " but this transaction expects to " +\
        "be signed by " + keyHash[0] + ". Exiting..."
      exit(1)
    signature = app.untrustedHashSign(keyPath, "")
    result['signatures'].append([binascii.hexlify(signature), signInput[1], signInput[0]])
    print result['signatures']

  return result

def createReturnJSON(app, dongle, result):
  body = {}
  body['_humans'] = "Generated by BTChip HW.1 wallet."
  body['content'] = json.dumps(result, sort_keys=True, separators=(',', ':'))

  rootKey = app.getWalletPublicKey(settings.KEYPATH_BASE)
  messageHash = sha256(body['content'])
  print "Message hash: %s. Ensure this hash matches what is returned by the dongle." % messageHash.encode('hex')
  body['signature_sha256'] = signMessage(app, dongle, settings.KEYPATH_BASE, messageHash.encode('hex'))
  body['signed_by'] = rootKey['address'] # Bug, should use network

  return body

def prettyPrintTX(txHex, isTestnet=False):
  network = 'XTN' if isTestnet else 'BTC'
  print "Transaction: "
  tx = pycoin.tx.Tx.tx_from_hex(txHex)
  print pycoin.scripts.tx.dump_tx(tx, network)

def prettyPrintRedeemScript(script, isTestnet=False):
  network = 'XTN' if isTestnet else 'BTC'
  script = pycoin.tx.pay_to.script_obj_from_script(bytearray(script.decode('hex'))).info(network)
  # pycoin transposed m and n for some reason
  print "%d of %d, %s" % (script['n'], script['m'], json.dumps(script['addresses']))
  pass

def sha256(x):
  return hashlib.sha256(x).digest()

if __name__ == "__main__":
  main()

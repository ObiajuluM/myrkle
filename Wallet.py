from decimal import Decimal
from typing import Union

from xrpl.asyncio.clients import AsyncJsonRpcClient
from xrpl.clients import JsonRpcClient
from xrpl.asyncio.ledger import get_fee
from xrpl.models import (AccountInfo, AccountLines, AccountNFTs, AccountTx, IssuedCurrencyAmount, Memo, NFTokenAcceptOffer,NFTokenCreateOffer, NFTokenCreateOfferFlag, Payment,PaymentFlag)
from xrpl.utils import drops_to_xrp, ripple_time_to_datetime, xrp_to_drops

from Misc import (is_hex, memo_builder, validate_hex_to_symbol, validate_symbol_to_hex,
                  xrp_format_to_nft_fee)

from x_constants import D_DATA, D_TYPE, M_SOURCE_TAG


def send_xrp( sender_addr: str, receiver_addr: str, amount: Union[float, Decimal, int],
    destination_tag: int = None, memo: Memo = None, fee: str = None) -> dict:
    """send xrp"""
    txn = Payment(
        account=sender_addr,
        amount=xrp_to_drops(amount),
        destination=receiver_addr,
        destination_tag=destination_tag,
        source_tag=M_SOURCE_TAG, fee=fee, memos=[memo])
    return txn.to_xrpl()

def send_token( sender_addr: str, receiver_addr: str, token: str, amount: str, issuer: str, partial: bool = False ,is_lp_token: bool = False,
    destination_tag: int = None, memo: Memo = None, fee: str = None) -> dict:
    """send asset...
    max amount = 15 decimal places"""
    cur = token if is_lp_token else validate_symbol_to_hex(token)
    flags = 0
    if partial:
        flags = PaymentFlag.TF_PARTIAL_PAYMENT.value
    txn = Payment(
        account=sender_addr,
        destination=receiver_addr,
        amount=IssuedCurrencyAmount(currency=cur, issuer=issuer, value=amount),
        destination_tag=destination_tag,
        fee=fee, flags=flags, 
        send_max=IssuedCurrencyAmount(currency=cur, issuer=issuer, value=amount),
        memos=[memo],
        source_tag=M_SOURCE_TAG)
    return txn.to_xrpl()



def send_nft(sender_addr: str, nftoken_id: str, receiver: str, memo: Memo = None, fee: str = None) -> dict:
    """send an nft"""
    txn = NFTokenCreateOffer(
        account=sender_addr,
        nftoken_id=nftoken_id,
        amount="0",
        destination=receiver,
        flags=NFTokenCreateOfferFlag.TF_SELL_NFTOKEN.value,
        memos=[memo],
        source_tag=M_SOURCE_TAG,
        fee=fee)
    return txn.to_xrpl()


def receive_nft(sender_addr: str, nft_sell_id: str, fee: str = None) -> dict:
    """receive an nft"""
    txn = NFTokenAcceptOffer(
        account=sender_addr, nftoken_sell_offer=nft_sell_id, fee=fee, source_tag=M_SOURCE_TAG, memos=[memo_builder(D_TYPE, D_DATA)])
    return txn.to_xrpl()



class xWallet(AsyncJsonRpcClient):
    def __init__(self, url: str) -> None:
        self.client = AsyncJsonRpcClient(url)

    async def get_network_fee(self) -> str:
        """return transaction fee, to populate interface and carry out transactions"""
        return await get_fee(self.client)

    async def xrp_balance(self, wallet_addr: str) -> dict:
        """return xrp balance and objects count"""
        _balance = 0
        owner_count = 0
        balance = 0
        acc_info = AccountInfo(account=wallet_addr, ledger_index="validated")
        response = await self.client.request(acc_info)
        result = response.result
        if "account_data" in result:
            _balance = int(result["account_data"]["Balance"]) - 10000000
            owner_count = int(result["account_data"]["OwnerCount"])
            balance = _balance - (2000000 * owner_count)
        return {
            "object_count": owner_count,
            "balance": str(drops_to_xrp(str(balance)))}

    async def xrp_transactions(self, wallet_addr: str) -> dict:
        """return all xrp payment transactions an address has carried out"""
        transactions_dict = {}
        sent = []
        received = []
        acc_tx = AccountTx(account=wallet_addr)
        response = await self.client.request(acc_tx)
        result = response.result
        if "transactions" in result:
            for transaction in result["transactions"]:
                if transaction["tx"]["TransactionType"] == "Payment":
                    transact = {}
                    transact["sender"] = transaction["tx"]["Account"]
                    transact["receiver"] = transaction["tx"]["Destination"]
                    transact["amount"] = str(drops_to_xrp(str(transaction["meta"]["delivered_amount"]))) if "delivered_amount" in transaction["meta"] and isinstance(transaction["meta"]["delivered_amount"], str) else str(drops_to_xrp(str(transaction["tx"]["Amount"])))
                    transact["fee"] = str(drops_to_xrp(str(transaction["tx"]["Fee"])))
                    transact["timestamp"] = str(ripple_time_to_datetime(transaction["tx"]["date"]))
                    transact["result"] = transaction["meta"]["TransactionResult"]
                    transact["txid"] = transaction["tx"]["hash"]
                    transact["tx_type"] = transaction["tx"]["TransactionType"]
                    # transact["memo"] = transaction["tx"]["Memo"] // this is a list that contains dicts 'parse later'
                    if transact["sender"] == wallet_addr:
                        sent.append(transact)
                    elif transact["sender"] != wallet_addr:
                        received.append(transact)
        transactions_dict["sent"] = sent
        transactions_dict["received"] = received
        return transactions_dict

    async def token_transactions(self, wallet_addr: str) -> dict:
        """return all token payment transactions an account has carried out"""
        transactions_dict = {}
        sent = []
        received = []
        acc_tx = AccountTx(account=wallet_addr)
        response = await self.client.request(acc_tx)
        result = response.result
        if "transactions" in result:
            for transaction in result["transactions"]:
                if transaction["tx"]["TransactionType"] == "Payment" and isinstance(transaction["tx"]["Amount"], dict):  
                    transact = {}
                    transact["sender"] = transaction["tx"]["Account"]
                    transact["receiver"] = transaction["tx"]["Destination"]
                    transact["token"] = validate_hex_to_symbol(transaction["meta"]["delivered_amount"]["currency"]) if "delivered_amount" in transaction["meta"] and isinstance(transaction["meta"]["delivered_amount"], dict) else validate_hex_to_symbol(transaction["tx"]["Amount"]["currency"])
                    transact["issuer"] = transaction["meta"]["delivered_amount"]["issuer"] if "delivered_amount" in transaction["meta"] and isinstance(transaction["meta"]["delivered_amount"], dict) else validate_hex_to_symbol(transaction["tx"]["Amount"]["issuer"])
                    transact["amount"] = transaction["meta"]["delivered_amount"]["value"] if "delivered_amount" in transaction["meta"] and isinstance(transaction["meta"]["delivered_amount"], dict) else validate_hex_to_symbol(transaction["tx"]["Amount"]["value"])
                    transact["fee"] = str(drops_to_xrp(str(transaction["tx"]["Fee"])))
                    transact["timestamp"] = str(ripple_time_to_datetime(transaction["tx"]["date"]))
                    transact["result"] = transaction["meta"]["TransactionResult"]
                    transact["txid"] = transaction["tx"]["hash"]
                    transact["tx_type"] = transaction["tx"]["TransactionType"]
                    # transact["memo"] = transaction["tx"]["Memo"] // this is a list that contains dicts 'parse later'
                    if transact["sender"] == wallet_addr:
                        sent.append(transact)
                    elif transact["sender"] != wallet_addr:
                        received.append(transact)
        transactions_dict["sent"] = sent
        transactions_dict["received"] = received
        return transactions_dict

    async def payment_transactions(self, wallet_addr: str) -> dict:
        """return all payment transactions for xrp and tokens both sent and received"""
        transactions = []
        acc_tx = AccountTx(account=wallet_addr)
        response = await self.client.request(acc_tx)
        result = response.result
        if "transactions" in result:
            for transaction in result["transactions"]:
                if transaction["tx"]["TransactionType"] == "Payment":
                    transact = {}
                    transact["sender"] = transaction["tx"]["Account"]
                    transact["receiver"] = transaction["tx"]["Destination"]
                    if isinstance(transaction["tx"]['Amount'], str):
                        transact["token"] = "XRP"
                        transact["issuer"] = ""
                        transact["amount"] = str(drops_to_xrp(str(transaction["meta"]["delivered_amount"]))) if "delivered_amount" in transaction["meta"] and isinstance(transaction["meta"]["delivered_amount"], str) else str(drops_to_xrp(str(transaction["tx"]["Amount"])))
                    if isinstance(transaction["tx"]["Amount"], dict) or "delivered_amount" in transaction["meta"] and isinstance(transaction["meta"]["delivered_amount"], dict):
                        transact["token"] = validate_hex_to_symbol(transaction["meta"]["delivered_amount"]["currency"]) if "delivered_amount" in transaction["meta"] and isinstance(transaction["meta"]["delivered_amount"], dict) else validate_hex_to_symbol(transaction["tx"]["Amount"]["currency"])
                        transact["issuer"] = transaction["meta"]["delivered_amount"]["issuer"] if "delivered_amount" in transaction["meta"] and isinstance(transaction["meta"]["delivered_amount"], dict) else validate_hex_to_symbol(transaction["tx"]["Amount"]["issuer"])
                        transact["amount"] = transaction["meta"]["delivered_amount"]["value"] if "delivered_amount" in transaction["meta"] and isinstance(transaction["meta"]["delivered_amount"], dict) else transaction["tx"]["Amount"]["value"]
                    transact["fee"] = str(drops_to_xrp(str(transaction["tx"]["Fee"])))
                    transact["timestamp"] = str(ripple_time_to_datetime(transaction["tx"]["date"]))
                    transact["result"] = transaction["meta"]["TransactionResult"]
                    transact["txid"] = transaction["tx"]["hash"]
                    transact["tx_type"] = transaction["tx"]["TransactionType"]
                    # transact["memo"] = transaction["tx"]["Memo"] // this is a list that contains dicts 'parse later'
                    transactions.append(transact)
        return transactions


    async def account_tokens(self, wallet_addr: str) -> list:
        """returns all tokens except LP tokens a wallet address is holding with their respective issuers, limit and balances"""
        assets = []
        acc_info = AccountLines(account=wallet_addr, ledger_index="validated")
        response = await self.client.request(acc_info)
        result = response.result
        if "lines" in result:
            lines = result["lines"]
            for line in lines:
                if isinstance(is_hex(line["currency"]), Exception):
                    pass
                else:
                    asset = {}
                    # filter lp tokens
                    asset["token"] = validate_hex_to_symbol(line["currency"])
                    asset["issuer"] = line["account"]
                    asset["amount"] = line["balance"]
                    asset["limit"] = line["limit"]  # the max an account can handle
                    asset["freeze_status"] = False
                    asset["ripple_status"] = False
                    if "no_ripple" in line:
                        asset["ripple_status"] = line["no_ripple"]  # no ripple = true, means rippling is disabled which is good; else bad
                    if "freeze" in line:
                        asset["freeze_status"] = line["freeze"]
                    """Query for domain and transfer rate with info.get_token_info()"""
                    assets.append(asset)
        return assets

    async def account_nfts(self, wallet_addr: str) -> list:
        "return all nfts an account is holding"
        account_nft = []
        acc_info = AccountNFTs(account=wallet_addr, id="validated")
        response = await self.client.request(acc_info)
        result = response.result
        if "account_nfts" in result:
            account_nfts = result["account_nfts"] 
            for nfts in account_nfts:
                nft = {}
                nft["flags"] = nfts["Flags"] if "Flags" in nfts else 0
                nft["issuer"] = nfts["Issuer"]
                nft["id"] = nfts["NFTokenID"]
                nft["taxon"] = nfts["NFTokenTaxon"]
                nft["serial"] = nfts["nft_serial"]
                nft["uri"] = validate_hex_to_symbol(nfts["URI"]) if "URI" in nfts else ""
                nft["transfer_fee"] = xrp_format_to_nft_fee(nfts["TransferFee"]) if "TransferFee" in nfts else 0
                account_nft.append(nft)
        return account_nft
    
    
    

# client = AsyncJsonRpcClient("http://s.devnet.rippletest.net:51234")
# client = AsyncJsonRpcClient("https://s.altnet.rippletest.net:51234")
client = JsonRpcClient("https://s.altnet.rippletest.net:51234")
d = xWallet(client.url)
# d = xWallet("https://xrplcluster.com")

# acc_info = AccountLines(account="rGiyqjWjhsRZ8FUjBL2k5ciUa2tcptTX9W", id="validated")
# response =  client.request(acc_info)
# result = response.result
# print(result)



# print(asyncio.run(  d.account_tokens(
#     "rGiyqjWjhsRZ8FUjBL2k5ciUa2tcptTX9W"
# )))


# issuer1 = Wallet.from_seed("sEdS1jTVU58HsPeL4xhPkziphnxFDHz")
# print("f")
# print(issuer1.classic_address)
# print("Ff")

# sender = Wallet.from_seed(seed= "sEdVdthdYnRRLqBXAD76QC7CatoLqU8")
# print(sender.classic_address)

# from xrpl.transaction.main  import autofill_and_sign, sign_and_submit

# def send_xrp( sender_addr: str, receiver_addr: str, amount: Union[float, Decimal, int],
#     destination_tag: int = None, memo: Memo = None, fee: str = None) -> dict:
#     """send xrp"""
#     txn = Payment(
#         account=sender_addr,
#         amount=xrp_to_drops(amount),
#         destination=receiver_addr,
#         destination_tag=destination_tag,
#         source_tag=M_SOURCE_TAG, fee=fee, memos=[memo],  flags=[
#             # PaymentFlag.TF_PARTIAL_PAYMENT, 
#             # PaymentFlag.TF_LIMIT_QUALITY,
            
#         ])
    
#     print(sign_and_submit(
#         txn, client, sender,
#     ).result["engine_result"])

# send_xrp(
#     amount=50000,
#     receiver_addr="rGiyqjWjhsRZ8FUjBL2k5ciUa2tcptTX9W",
#     sender_addr=sender.classic_address,
# )

# def send_token( sender_addr: str, receiver_addr: str, token: str, amount: str, issuer: str, partial: bool = False ,is_lp_token: bool = False,
#     destination_tag: int = None, memo: Memo = None, fee: str = None) -> dict:
#     """send asset...
#     max amount = 15 decimal places"""
#     cur = token if is_lp_token else validate_symbol_to_hex(token)
#     flags = 0
#     if partial:
#         flags = PaymentFlag.TF_PARTIAL_PAYMENT
#     txn = Payment(
#         account=sender_addr,
#         destination=receiver_addr,
#         amount=IssuedCurrencyAmount(currency=cur, issuer=issuer, value=amount),
#         destination_tag=destination_tag,
#         fee=fee, flags=flags, 
#         send_max=IssuedCurrencyAmount(currency=cur, issuer=issuer, value=amount),
#         memos=[memo],
#         source_tag=M_SOURCE_TAG)
#     print(sign_and_submit(
#         txn, client, issuer1,
#     ).result["engine_result"])

# send_token(
#     partial=True,
     

#     amount=10, 
#       token="NGN", issuer="rHTfx7p4ge8CfDhyoczpSwc84LWfiK3dhN",
#     sender_addr=issuer1.classic_address,
    
    
#     receiver_addr="rDtnYC916KsnYmNsy1mGJt6KWuTYUFFCgY"
# )


# acc_tx = AccountTx(account="rGiyqjWjhsRZ8FUjBL2k5ciUa2tcptTX9W")
# response =  client.request(acc_tx)

# with open("txn.json", "wt") as stream:
#     json.dump(response.result, stream)

# print(asyncio.run(
#     d.xrp_transactions(
#         "rGiyqjWjhsRZ8FUjBL2k5ciUa2tcptTX9W"
#     )   
# ))



# print(send_token(
#     "rGiyqjWjhsRZ8FUjBL2k5ciUa2tcptTX9W",
# "rqga9EVfFAj2HJMwmFVccDS6zgXrRgh9j",
# "USD", "10", "rBZJzEisyXt2gvRWXLxHftFRkd1vJEpBQP", True
# ))
    
print(send_xrp(
    "rGiyqjWjhsRZ8FUjBL2k5ciUa2tcptTX9W",
    "rHiyqjWjhsRZ8FUjBL2k5ciUa2tcptTX9W",
    20.0,
    1001010,
    memo_builder("note", "TextRP prize winning")
))



# pp = send_nft(
#     "rGiyqjWjhsRZ8FUjBL2k5ciUa2tcptTX9W", "00080000ADFDB77A8B3A255EB4DEC33759232E724309D0700000099A00000000", "rBZJzEisyXt2gvRWXLxHftFRkd1vJEpBQP"
# )

# print(pp)



# import json

# # Serializing json
# json_object = json.dumps(pp, indent=4)
 
# # Writing to sample.json
# with open("wsof.json", "w") as outfile:
#     outfile.write(json_object)



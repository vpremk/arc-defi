import os
import time
from circle.web3 import developer_controlled_wallets, utils
from dotenv import load_dotenv
from web3 import Web3

load_dotenv()

# Initialize Circle ARC client
circle_client = utils.init_developer_controlled_wallets_client(
    api_key=os.getenv("CIRCLE_API_KEY"),
    entity_secret=os.getenv("CIRCLE_ENTITY_SECRET")
)
wallet_sets_api = developer_controlled_wallets.WalletSetsApi(circle_client)
wallets_api = developer_controlled_wallets.WalletsApi(circle_client)
transactions_api = developer_controlled_wallets.TransactionsApi(circle_client)

web3 = Web3(Web3.HTTPProvider("https://rpc.testnet.arc.network"))

# Constants
NFT_CONTRACT = "0xD8E3280E63b3a29cF12b01d8AB45f43CB539E0Dd"
USDC_ADDRESS = "0x3600000000000000000000000000000000000000"
ASSET_ADDRESS = "0x6f7D1941775e1400f81Ebb03c1E9F757d9Cd2deE"  # TestNFT

ERC20_ABI = [
    {"inputs": [{"internalType": "address", "name": "spender", "type": "address"}, {"internalType": "uint256", "name": "amount", "type": "uint256"}],
     "name": "approve", "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
     "stateMutability": "nonpayable", "type": "function"}
]

NFT_ABI = [
    {"inputs": [{"internalType": "address", "name": "_stablecoin", "type": "address"}, {"internalType": "address", "name": "_assetToken", "type": "address"}],
     "stateMutability": "nonpayable", "type": "constructor"},
    {"inputs": [], "name": "admin", "outputs": [{"internalType": "address", "name": "", "type": "address"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "tradeId", "type": "uint256"}, {"internalType": "uint256", "name": "additionalMargin", "type": "uint256"}],
     "name": "adjustMargin", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"internalType": "address", "name": "buyer", "type": "address"}, {"internalType": "address", "name": "seller", "type": "address"},
     {"internalType": "uint256", "name": "assetId", "type": "uint256"}, {"internalType": "uint256", "name": "price", "type": "uint256"},
     {"internalType": "uint256", "name": "margin", "type": "uint256"}], "name": "createTrade", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
     "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "tradeId", "type": "uint256"}], "name": "executeTrade", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [], "name": "nextTradeId", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "stablecoin", "outputs": [{"internalType": "contract IERC20", "name": "", "type": "address"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "tradeId", "type": "uint256"}, {"internalType": "contract IERC20", "name": "newToken", "type": "address"},
     {"internalType": "uint256", "name": "amount", "type": "uint256"}], "name": "substituteCollateral", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "name": "trades",
     "outputs": [{"internalType": "address", "name": "buyer", "type": "address"}, {"internalType": "address", "name": "seller", "type": "address"},
     {"internalType": "uint256", "name": "assetId", "type": "uint256"}, {"internalType": "uint256", "name": "price", "type": "uint256"},
     {"internalType": "uint256", "name": "marginPosted", "type": "uint256"}, {"internalType": "bool", "name": "executed", "type": "bool"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "assetToken", "outputs": [{"internalType": "contract IERC721", "name": "", "type": "address"}], "stateMutability": "view", "type": "function"}
]

nft_contract = web3.eth.contract(address=NFT_CONTRACT, abi=NFT_ABI)
usdc_contract = web3.eth.contract(address=USDC_ADDRESS, abi=ERC20_ABI)

def wait_for_tx(tx_id, api):
    while True:
        status = api.get_transaction(tx_id).data.transaction.state
        if status == 'CONFIRMED':
            break
        elif status == 'FAILED':
            raise Exception(f"Transaction {tx_id} failed")
        time.sleep(5)

# Test NFT Trade
print("Testing NFT Trade on CollateralizedTradeERC8183.sol")

BUYER_ADDRESS = Web3.to_checksum_address("0x0862ce09fa64c8496cdafad9320bb8f67c7d25ab")
SELLER_ADDRESS = Web3.to_checksum_address("0xefb5db9a28a202614a113d6a5c492d02aad9217d")

buyer_wallet = wallets_api.get_wallets(address=BUYER_ADDRESS).data.wallets[0].actual_instance
seller_wallet = wallets_api.get_wallets(address=SELLER_ADDRESS).data.wallets[0].actual_instance

buyer_address = Web3.to_checksum_address(buyer_wallet.address)
seller_address = Web3.to_checksum_address(seller_wallet.address)
web3.eth.default_account = buyer_address

print(f"Buyer Wallet: {buyer_address}")
print(f"Seller Wallet: {seller_address}")

# Fund buyer with USDC (manual step)
print("Fund the buyer wallet with USDC from https://faucet.circle.com/")
input("Press Enter after funding...")

# Transfer NFT to seller (assuming deployer owns it)
# First, approve and transfer NFT from deployer to seller
# But since deployer is not in Circle wallets, need to use web3 or something, but for simplicity, assume seller has the NFT.

# For test, assume seller has token ID 1. If not, transfer it.

# Create job
# job = transactions_api.create_job({"name": "NFT Trade Test", "description": "Test NFT collateralized trade"})
job_id = None  # For test, no job

# Create trade
print("Creating NFT trade...")
approve_data = usdc_contract.functions.approve(NFT_CONTRACT, 1000000).build_transaction({'from': buyer_address})['data']
approve_req = developer_controlled_wallets.CreateContractExecutionTransactionForDeveloperRequest.from_dict({
    "walletId": buyer_wallet.id, "contractAddress": USDC_ADDRESS, "callData": approve_data, "feeLevel": "MEDIUM"
})
approve_tx = transactions_api.create_developer_transaction_contract_execution(approve_req)
wait_for_tx(approve_tx.data.id, transactions_api)

create_data = nft_contract.functions.createTrade(buyer_address, seller_address, 1, 5000000, 1000000).build_transaction({'from': buyer_address})['data']
create_req = developer_controlled_wallets.CreateContractExecutionTransactionForDeveloperRequest.from_dict({
    "walletId": buyer_wallet.id, "contractAddress": NFT_CONTRACT, "callData": create_data, "feeLevel": "MEDIUM"
})
create_tx = transactions_api.create_developer_transaction_contract_execution(create_req)
wait_for_tx(create_tx.data.id, transactions_api)
print("NFT trade created")

# Execute trade
print("Executing NFT trade...")
execute_data = nft_contract.functions.executeTrade(0).build_transaction({'from': buyer_address})['data']
execute_req = developer_controlled_wallets.CreateContractExecutionTransactionForDeveloperRequest.from_dict({
    "walletId": buyer_wallet.id, "contractAddress": NFT_CONTRACT, "callData": execute_data, "feeLevel": "MEDIUM"
})
execute_tx = transactions_api.create_developer_transaction_contract_execution(execute_req)
wait_for_tx(execute_tx.data.id, transactions_api)
print("NFT trade executed")

print("Test completed!")
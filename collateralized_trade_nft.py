import os
import sys
import time
from circle.web3 import developer_controlled_wallets, utils
from dotenv import load_dotenv
from web3 import Web3

load_dotenv()

# 1. Initialize Circle ARC client
circle_client = utils.init_developer_controlled_wallets_client(
    api_key=os.getenv("CIRCLE_API_KEY"),
    entity_secret=os.getenv("CIRCLE_ENTITY_SECRET")
)
wallet_sets_api = developer_controlled_wallets.WalletSetsApi(circle_client)
wallets_api = developer_controlled_wallets.WalletsApi(circle_client)
transactions_api = developer_controlled_wallets.TransactionsApi(circle_client)

web3 = Web3(Web3.HTTPProvider("https://rpc.testnet.arc.network"))

# 2. Set constants
TRADE_CONTRACT = "0xe185f2E0ebf96638bfCe09FC6b77d36d17FCC32c"  # Deployed contract address
INITIAL_MARGIN = "1000000"  # 1 USDC (6 decimals)
JOB_BUDGET = "5000000"      # 5 USDC
ASSET_ID = "1"              # NFT token ID
TRADE_PRICE = "5000000"     # 5 USDC
USDC_ADDRESS = "0xYOUR_USDC_ADDRESS"  # USDC contract address
ASSET_ADDRESS = "0xYOUR_ASSET_ADDRESS"  # Asset NFT contract address

# Mock ABI for contract calls (replace with actual ABI)
ERC20_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "spender", "type": "address"}, {"internalType": "uint256", "name": "amount", "type": "uint256"}],
        "name": "approve",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

TRADE_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "_stablecoin", "type": "address"},
            {"internalType": "address", "name": "_assetToken", "type": "address"}
        ],
        "stateMutability": "nonpayable",
        "type": "constructor"
    },
    {
        "inputs": [],
        "name": "admin",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "assetToken",
        "outputs": [{"internalType": "contract IERC721", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "tradeId", "type": "uint256"},
            {"internalType": "uint256", "name": "additionalMargin", "type": "uint256"}
        ],
        "name": "adjustMargin",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "buyer", "type": "address"},
            {"internalType": "address", "name": "seller", "type": "address"},
            {"internalType": "uint256", "name": "assetId", "type": "uint256"},
            {"internalType": "uint256", "name": "price", "type": "uint256"},
            {"internalType": "uint256", "name": "margin", "type": "uint256"}
        ],
        "name": "createTrade",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "tradeId", "type": "uint256"}
        ],
        "name": "executeTrade",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "nextTradeId",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "stablecoin",
        "outputs": [{"internalType": "contract IERC20", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "tradeId", "type": "uint256"},
            {"internalType": "contract IERC20", "name": "newToken", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"}
        ],
        "name": "substituteCollateral",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "", "type": "uint256"}
        ],
        "name": "trades",
        "outputs": [
            {"internalType": "address", "name": "buyer", "type": "address"},
            {"internalType": "address", "name": "seller", "type": "address"},
            {"internalType": "uint256", "name": "assetId", "type": "uint256"},
            {"internalType": "uint256", "name": "price", "type": "uint256"},
            {"internalType": "uint256", "name": "marginPosted", "type": "uint256"},
            {"internalType": "bool", "name": "executed", "type": "bool"}
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

trade_contract = web3.eth.contract(address=TRADE_CONTRACT, abi=TRADE_ABI)
usdc_contract = web3.eth.contract(address=USDC_ADDRESS, abi=ERC20_ABI)

def wait_for_tx(tx_id, api):
    while True:
        status = api.get_transaction(tx_id).status
        if status == 'confirmed':
            break
        elif status == 'failed':
            raise Exception(f"Transaction {tx_id} failed")
        time.sleep(5)

# 3. Workflow steps

# Step 1: Create wallets for buyer & seller
print("Step 1: Creating wallets for buyer & seller")
buyer_wallet_set = wallet_sets_api.create_wallet_set({"name": "Buyer Wallet Set"})
buyer_wallet = wallets_api.create_wallet(buyer_wallet_set.id, {"name": "Buyer Wallet"})

seller_wallet_set = wallet_sets_api.create_wallet_set({"name": "Seller Wallet Set"})
seller_wallet = wallets_api.create_wallet(seller_wallet_set.id, {"name": "Seller Wallet"})

print(f"Buyer Wallet ID: {buyer_wallet.id}, Address: {buyer_wallet.address}")
print(f"Seller Wallet ID: {seller_wallet.id}, Address: {seller_wallet.address}")

# Check initial balances
buyer_balance = wallets_api.get_wallet(buyer_wallet.id).balance
seller_balance = wallets_api.get_wallet(seller_wallet.id).balance
print(f"Initial Buyer Balance: {buyer_balance} USDC")
print(f"Initial Seller Balance: {seller_balance} USDC")

# Step 2: Fund buyer wallet
print("\nStep 2: Funding buyer wallet")
# In testnet, fund via faucet or external means. Assuming funded with USDC.

# Step 3: Transfer initial collateral to seller (starter balance)
print("\nStep 3: Transfer initial collateral to seller")
transfer_tx = transactions_api.create_transaction({
    "wallet_id": buyer_wallet.id,
    "to": seller_wallet.address,
    "amount": INITIAL_MARGIN,
    "token": "USDC"
})
print(f"Transfer TX ID: {transfer_tx.id}")
wait_for_tx(transfer_tx.id, transactions_api)
print("Transfer confirmed")

# Step 4: Create job (represents trade execution)
print("\nStep 4: Creating job")
job = transactions_api.create_job({
    "name": "Collateralized NFT Trade",
    "description": "DeFi trade with NFT collateral lifecycle"
})
print(f"Job ID: {job.id}")

# Step 5: Set budget (trade notional)
print("\nStep 5: Setting budget")
budget = transactions_api.set_budget(job.id, {
    "amount": JOB_BUDGET,
    "token": "USDC"
})
print(f"Budget set: {budget.amount} USDC")

# Step 6: Approve USDC for trade (pre-funding / margin approval)
print("\nStep 6: Approving USDC for trade")
approve_data = usdc_contract.functions.approve(TRADE_CONTRACT, int(INITIAL_MARGIN)).build_transaction()['data']
approve_tx = transactions_api.create_transaction({
    "job_id": job.id,
    "wallet_id": buyer_wallet.id,
    "to": USDC_ADDRESS,
    "data": approve_data,
    "amount": "0",
    "token": "ETH"  # Native for gas
})
print(f"Approve TX ID: {approve_tx.id}")
wait_for_tx(approve_tx.id, transactions_api)
print("Approve confirmed")

# Step 7: Create trade (initial margin posting / clearing)
print("\nStep 7: Creating trade")
create_data = trade_contract.functions.createTrade(
    buyer_wallet.address, seller_wallet.address, int(ASSET_ID), int(TRADE_PRICE), int(INITIAL_MARGIN)
).build_transaction()['data']
create_tx = transactions_api.create_transaction({
    "job_id": job.id,
    "wallet_id": buyer_wallet.id,  # Assuming buyer wallet is admin
    "to": TRADE_CONTRACT,
    "data": create_data,
    "amount": "0",
    "token": "ETH"
})
print(f"Create Trade TX ID: {create_tx.id}")
wait_for_tx(create_tx.id, transactions_api)
print("Trade created")
trade_id = 0  # Assuming first trade

# Step 8: Adjust margin (variation margin)
print("\nStep 8: Adjusting margin")
variation_amount = 500000  # 0.5 USDC
adjust_data = trade_contract.functions.adjustMargin(trade_id, variation_amount).build_transaction()['data']
adjust_tx = transactions_api.create_transaction({
    "job_id": job.id,
    "wallet_id": buyer_wallet.id,
    "to": TRADE_CONTRACT,
    "data": adjust_data,
    "amount": "0",
    "token": "ETH"
})
print(f"Adjust TX ID: {adjust_tx.id}")
wait_for_tx(adjust_tx.id, transactions_api)
print("Margin adjusted")

# Step 9: Substitute collateral if needed
print("\nStep 9: Substituting collateral")
new_token = "0xNEW_TOKEN_ADDRESS"  # Placeholder
substitute_amount = 1000000
# First, approve new token
new_token_contract = web3.eth.contract(address=new_token, abi=ERC20_ABI)
approve_new_data = new_token_contract.functions.approve(TRADE_CONTRACT, substitute_amount).build_transaction()['data']
approve_new_tx = transactions_api.create_transaction({
    "job_id": job.id,
    "wallet_id": buyer_wallet.id,
    "to": new_token,
    "data": approve_new_data,
    "amount": "0",
    "token": "ETH"
})
print(f"Approve New Token TX ID: {approve_new_tx.id}")
wait_for_tx(approve_new_tx.id, transactions_api)
print("New token approved")

substitute_data = trade_contract.functions.substituteCollateral(trade_id, new_token, substitute_amount).build_transaction()['data']
substitute_tx = transactions_api.create_transaction({
    "job_id": job.id,
    "wallet_id": buyer_wallet.id,
    "to": TRADE_CONTRACT,
    "data": substitute_data,
    "amount": "0",
    "token": "ETH"
})
print(f"Substitute TX ID: {substitute_tx.id}")
wait_for_tx(substitute_tx.id, transactions_api)
print("Collateral substituted")

# Step 10: Execute trade (final DVP settlement)
print("\nStep 10: Executing trade")
execute_data = trade_contract.functions.executeTrade(trade_id).build_transaction()['data']
execute_tx = transactions_api.create_transaction({
    "job_id": job.id,
    "wallet_id": buyer_wallet.id,
    "to": TRADE_CONTRACT,
    "data": execute_data,
    "amount": "0",
    "token": "ETH"
})
print(f"Execute TX ID: {execute_tx.id}")
wait_for_tx(execute_tx.id, transactions_api)
print("Trade executed")

# Step 11: Print final balances and job status
print("\nStep 11: Final balances and job status")
buyer_wallet_info = wallets_api.get_wallet(buyer_wallet.id)
seller_wallet_info = wallets_api.get_wallet(seller_wallet.id)
job_info = transactions_api.get_job(job.id)

print(f"Buyer Balance: {buyer_wallet_info.balance} USDC")
print(f"Seller Balance: {seller_wallet_info.balance} USDC")
print(f"Job Status: {job_info.status}")
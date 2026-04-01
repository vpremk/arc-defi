import os
from web3 import Web3
from dotenv import load_dotenv
from solcx import compile_source, install_solc

load_dotenv()

# Configuration
RPC_URL = "https://rpc.testnet.arc.network"  # Circle ARC testnet RPC
CONTRACT_FILE = "CollateralizedTradeERC8183.sol"  # "CollateralizedTrade.sol" for ERC-20, "CollateralizedTradeERC8183.sol" for NFT, "TestNFT.sol" for test NFT
CONTRACT_NAME = "CollateralizedTradeERC8183"  # "CollateralizedTrade" or "CollateralizedTradeERC8183" or "TestNFT"

# Connect to network early for checksum
web3 = Web3(Web3.HTTPProvider(RPC_URL))

# Constructor args: for TestNFT, none; for trades, stablecoin and asset
if CONTRACT_NAME == "TestNFT":
    CONSTRUCTOR_ARGS = []
else:
    USDC_ADDRESS = "0x3600000000000000000000000000000000000000"  # USDC on Circle ARC testnet
    ASSET_ADDRESS = "0x6f7D1941775e1400f81Ebb03c1E9F757d9Cd2deE"  # Deployed TestNFT address
    CONSTRUCTOR_ARGS = [
        web3.to_checksum_address(USDC_ADDRESS),
        web3.to_checksum_address(ASSET_ADDRESS)
    ]

# Install solc if needed
try:
    compile_source("pragma solidity ^0.8.0; contract Test {}", solc_binary='/opt/homebrew/bin/solc')
except Exception:
    print("Solc not found. Please install via 'brew install solidity'")
    exit(1)

# Connect to network
# web3 = Web3(Web3.HTTPProvider(RPC_URL))  # Moved up

# Load private key
private_key = os.getenv("PRIVATE_KEY")
if not private_key:
    raise ValueError("Set PRIVATE_KEY in .env")
account = web3.eth.account.from_key(private_key)
web3.eth.default_account = account.address

print(f"Deploying from account: {account.address}")
print(f"Account balance: {web3.from_wei(web3.eth.get_balance(account.address), 'ether')} ETH")

# Read and compile contract
with open(CONTRACT_FILE, 'r') as f:
    source = f.read()

compiled = compile_source(source, solc_binary='/opt/homebrew/bin/solc')
contract_key = f'<stdin>:{CONTRACT_NAME}'
if contract_key not in compiled:
    raise ValueError(f"Contract {CONTRACT_NAME} not found in {CONTRACT_FILE}")

abi = compiled[contract_key]['abi']
bytecode = compiled[contract_key]['bin']

# Deploy
contract = web3.eth.contract(abi=abi, bytecode=bytecode)
tx = contract.constructor(*CONSTRUCTOR_ARGS).build_transaction({
    'gas': 3000000,
    'gasPrice': web3.eth.gas_price,
    'nonce': web3.eth.get_transaction_count(account.address),
})

signed_tx = web3.eth.account.sign_transaction(tx, private_key)
tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

print(f"Contract deployed at: {receipt.contractAddress}")
print(f"Transaction hash: {tx_hash.hex()}")
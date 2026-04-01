import os
import sys
import time

from circle.web3 import developer_controlled_wallets, utils
from dotenv import load_dotenv
from web3 import Web3

load_dotenv()

# Bootstrap the provider wallet from the client wallet to avoid a second faucet request.
PROVIDER_STARTER_BALANCE = "1"

AGENTIC_COMMERCE_CONTRACT = "0x0747EEf0706327138c69792bF28Cd525089e4583"
JOB_BUDGET = "5000000" # 5 USDC (ERC-20, 6 decimals)

# ERC-721 Collateralized Trade Contract (deploy separately or use placeholder)
NFT_CONTRACT = "0xD8E3280E63b3a29cF12b01d8AB45f43CB539E0Dd"  # Deployed ERC-721 contract address
USDC_ADDRESS = "0x3600000000000000000000000000000000000000"  # USDC on ARC testnet

ERC20_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "spender", "type": "address"}, {"internalType": "uint256", "name": "amount", "type": "uint256"}],
        "name": "approve",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

NFT_ABI = [
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
    },
    {
        "inputs": [],
        "name": "assetToken",
        "outputs": [{"internalType": "contract IERC721", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    }
]

circle_client = utils.init_developer_controlled_wallets_client(
    api_key=os.getenv("CIRCLE_API_KEY"),
    entity_secret=os.getenv("CIRCLE_ENTITY_SECRET"),
)

wallet_sets_api = developer_controlled_wallets.WalletSetsApi(circle_client)
wallets_api = developer_controlled_wallets.WalletsApi(circle_client)
transactions_api = developer_controlled_wallets.TransactionsApi(circle_client)

web3 = Web3(Web3.HTTPProvider("https://rpc.testnet.arc.network"))

nft_contract = web3.eth.contract(address=NFT_CONTRACT, abi=NFT_ABI)
usdc_contract = web3.eth.contract(address=USDC_ADDRESS, abi=ERC20_ABI)

agentic_commerce_abi = [
    {
        "type": "function",
        "name": "getJob",
        "stateMutability": "view",
        "inputs": [{"name": "jobId", "type": "uint256"}],
        "outputs": [
            {
                "type": "tuple",
                "components": [
                    {"name": "id", "type": "uint256"},
                    {"name": "client", "type": "address"},
                    {"name": "provider", "type": "address"},
                    {"name": "evaluator", "type": "address"},
                    {"name": "description", "type": "string"},
                    {"name": "budget", "type": "uint256"},
                    {"name": "expiredAt", "type": "uint256"},
                    {"name": "status", "type": "uint8"},
                    {"name": "hook", "type": "address"},
                ],
            }
        ],
    },
    {
        "type": "event",
        "name": "JobCreated",
        "inputs": [
            {"indexed": True, "name": "jobId", "type": "uint256"},
            {"indexed": True, "name": "client", "type": "address"},
            {"indexed": True, "name": "provider", "type": "address"},
            {"indexed": False, "name": "evaluator", "type": "address"},
            {"indexed": False, "name": "expiredAt", "type": "uint256"},
            {"indexed": False, "name": "hook", "type": "address"},
        ],
        "anonymous": False,
    },
]

STATUS_NAMES = [
    "Open",
    "Funded",
    "Submitted",
    "Completed",
    "Rejected",
    "Expired",
]


def extract_job_id(tx_hash: str) -> int:
    contract = web3.eth.contract(
        address=Web3.to_checksum_address(AGENTIC_COMMERCE_CONTRACT),
        abi=agentic_commerce_abi,
    )
    receipt = web3.eth.get_transaction_receipt(tx_hash)
    logs = contract.events.JobCreated().process_receipt(receipt)

    if not logs:
        raise RuntimeError("Could not parse JobCreated event")

    return int(logs[0]["args"]["jobId"])


def wait_for_transaction(tx_id: str, label: str) -> str:
    sys.stdout.write(f"  Waiting for {label}")
    sys.stdout.flush()

    for _ in range(60):
        time.sleep(2)
        tx = transactions_api.get_transaction(id=tx_id)
        transaction = tx.data.transaction

        if transaction.state == "COMPLETE" and transaction.tx_hash:
            tx_hash = transaction.tx_hash
            print(f" ✓\n  Tx: https://testnet.arcscan.app/tx/{tx_hash}")
            return tx_hash
        if transaction.state == "FAILED":
            raise RuntimeError(f"{label} failed onchain")

        sys.stdout.write(".")
        sys.stdout.flush()

    raise RuntimeError(f"{label} timed out")


def print_balances(title: str, wallets: list[dict[str, str]]) -> None:
    print(f"\n{title}:")

    for wallet in wallets:
        balances = wallets_api.list_wallet_balance(id=wallet["id"])
        usdc_amount = "0"

        for entry in balances.data.token_balances or []:
            balance = getattr(entry, "actual_instance", entry)
            token = getattr(balance, "token", None)
            token = getattr(token, "actual_instance", token)

            if token and getattr(token, "symbol", None) == "USDC":
                usdc_amount = getattr(balance, "amount", "0")
                break

        print(f"  {wallet['label']}: {wallet['address']}")
        print(f"    USDC: {usdc_amount}")


def main() -> None:
    print("── Step 1: Create wallets ──")

    wallet_set = wallet_sets_api.create_wallet_set(
        developer_controlled_wallets.CreateWalletSetRequest.from_dict({
            "name": "ERC8183 Job Wallets",
        })
    )

    wallets_response = wallets_api.create_wallet(
        developer_controlled_wallets.CreateWalletRequest.from_dict({
            "blockchains": ["ARC-TESTNET"],
            "count": 2,
            "walletSetId": wallet_set.data.wallet_set.actual_instance.id,
            "accountType": "SCA",
        })
    )

    client_wallet = wallets_response.data.wallets[0].actual_instance
    provider_wallet = wallets_response.data.wallets[1].actual_instance

    print("\n── Step 2: Fund the client wallet ──")
    print("  Fund this wallet with Arc Testnet USDC:")
    print(f"  Client/Buy Side Firm: {client_wallet.address}")
    print(f"  Wallet ID: {client_wallet.id}")
    print("  Public faucet:  https://faucet.circle.com")
    print("  Console faucet: https://console.circle.com/faucet")
    print("\n  This script will fund the provider wallet automatically.")
    input("\nPress Enter after the client wallet is funded... ")

    print("\n── Step 3: Transfer starter USDC to provider ──")
    transfer_request = (
        developer_controlled_wallets.CreateTransferTransactionForDeveloperRequest.from_dict(
            {
                "walletAddress": client_wallet.address,
                "blockchain": "ARC-TESTNET",
                "tokenAddress": "0x3600000000000000000000000000000000000000",
                "destinationAddress": provider_wallet.address,
                "amounts": [PROVIDER_STARTER_BALANCE],
                "feeLevel": "MEDIUM",
            }
        )
    )
    transfer_response = transactions_api.create_developer_transaction_transfer(
        create_transfer_transaction_for_developer_request=transfer_request
    )
    wait_for_transaction(
        transfer_response.data.id,
        "transfer starter USDC to provider",
    )

    print("\n── Step 4: Check balances ──")
    print_balances(
        "Balances",
        [
            {"label": "Client", "address": client_wallet.address, "id": client_wallet.id},
            {"label": "Provider", "address": provider_wallet.address, "id": provider_wallet.id},
        ],
    )

    expired_at = web3.eth.get_block("latest")["timestamp"] + 3600

    print("\n── Step 5: Create job - Trade execution (order matched) ──")
    create_job_request = (
        developer_controlled_wallets.CreateContractExecutionTransactionForDeveloperRequest.from_dict(
            {
                "walletAddress": client_wallet.address,
                "blockchain": "ARC-TESTNET",
                "contractAddress": AGENTIC_COMMERCE_CONTRACT,
                "abiFunctionSignature": "createJob(address,address,uint256,string,address)",
                "abiParameters": [
                    provider_wallet.address,
                    client_wallet.address,
                    str(expired_at),
                    "ERC-8183 demo job on Arc Testnet",
                    "0x0000000000000000000000000000000000000000",
                ],
                "feeLevel": "MEDIUM",
            }
        )
    )
    create_job_response = transactions_api.create_developer_transaction_contract_execution(
        create_job_request
    )
    create_job_tx_hash = wait_for_transaction(
        create_job_response.data.id,
        "create job",
    )
    job_id = extract_job_id(create_job_tx_hash)
    print(f"  Job ID: {job_id}")

    print("\n── Step 6: Set budget - Trade notional / contract value──")
    set_budget_request = (
        developer_controlled_wallets.CreateContractExecutionTransactionForDeveloperRequest.from_dict(
            {
                "walletAddress": provider_wallet.address,
                "blockchain": "ARC-TESTNET",
                "contractAddress": AGENTIC_COMMERCE_CONTRACT,
                "abiFunctionSignature": "setBudget(uint256,uint256,bytes)",
                "abiParameters": [str(job_id), JOB_BUDGET, "0x"],
                "feeLevel": "MEDIUM",
            }
        )
    )
    set_budget_response = transactions_api.create_developer_transaction_contract_execution(
        set_budget_request
    )
    wait_for_transaction(set_budget_response.data.id, "set budget")

    print("\n── Step 7: Approve USDC - Pre-funding / margin approval ──")
    approve_request = (
        developer_controlled_wallets.CreateContractExecutionTransactionForDeveloperRequest.from_dict(
            {
                "walletAddress": client_wallet.address,
                "blockchain": "ARC-TESTNET",
                "contractAddress": "0x3600000000000000000000000000000000000000",
                "abiFunctionSignature": "approve(address,uint256)",
                "abiParameters": [AGENTIC_COMMERCE_CONTRACT, JOB_BUDGET],
                "feeLevel": "MEDIUM",
            }
        )
    )
    approve_response = transactions_api.create_developer_transaction_contract_execution(
        approve_request
    )
    wait_for_transaction(approve_response.data.id, "approve USDC")

    print("\n── Step 8: Fund escrow - Clearing (margin posted to CCP) ──")
    fund_request = (
        developer_controlled_wallets.CreateContractExecutionTransactionForDeveloperRequest.from_dict(
            {
                "walletAddress": client_wallet.address,
                "blockchain": "ARC-TESTNET",
                "contractAddress": AGENTIC_COMMERCE_CONTRACT,
                "abiFunctionSignature": "fund(uint256,bytes)",
                "abiParameters": [str(job_id), "0x"],
                "feeLevel": "MEDIUM",
            }
        )
    )
    fund_response = transactions_api.create_developer_transaction_contract_execution(
        fund_request
    )
    wait_for_transaction(fund_response.data.id, "fund escrow")

    print("\n── Step 9: Submit deliverable - Trade confirmation / delivery obligation ──")
    deliverable_hash = Web3.to_hex(
        Web3.keccak(text="arc-erc8183-demo-deliverable")
    )
    submit_request = (
        developer_controlled_wallets.CreateContractExecutionTransactionForDeveloperRequest.from_dict(
            {
                "walletAddress": provider_wallet.address,
                "blockchain": "ARC-TESTNET",
                "contractAddress": AGENTIC_COMMERCE_CONTRACT,
                "abiFunctionSignature": "submit(uint256,bytes32,bytes)",
                "abiParameters": [str(job_id), deliverable_hash, "0x"],
                "feeLevel": "MEDIUM",
            }
        )
    )
    submit_response = transactions_api.create_developer_transaction_contract_execution(
        submit_request
    )
    wait_for_transaction(submit_response.data.id, "submit deliverable")

    print("\n── Step 10: Complete job -Final settlement (DVP)──")
    reason_hash = Web3.to_hex(Web3.keccak(text="deliverable-approved"))
    complete_request = (
        developer_controlled_wallets.CreateContractExecutionTransactionForDeveloperRequest.from_dict(
            {
                "walletAddress": client_wallet.address,
                "blockchain": "ARC-TESTNET",
                "contractAddress": AGENTIC_COMMERCE_CONTRACT,
                "abiFunctionSignature": "complete(uint256,bytes32,bytes)",
                "abiParameters": [str(job_id), reason_hash, "0x"],
                "feeLevel": "MEDIUM",
            }
        )
    )
    complete_response = transactions_api.create_developer_transaction_contract_execution(
        complete_request
    )
    wait_for_transaction(complete_response.data.id, "complete job")

    print("\n── Step 11: Check final job state ──")
    contract = web3.eth.contract(
        address=Web3.to_checksum_address(AGENTIC_COMMERCE_CONTRACT),
        abi=agentic_commerce_abi,
    )
    job = contract.functions.getJob(job_id).call()
    print(f"  Job ID: {job_id}")
    print(f"  Status: {STATUS_NAMES[int(job[7])]}")
    print(f"  Budget: {Web3.from_wei(job[5], 'mwei')} USDC")
    print(f"  Hook: {job[8]}")
    print(f"  Deliverable hash submitted: {deliverable_hash}")

    print("\n── Step 12: Check final balances ──")
    print_balances(
        "Balances",
        [
            {"label": "Client/Buy-Side Firm", "address": client_wallet.address, "id": client_wallet.id},
            {"label": "Provider/Sell-Side Firm", "address": provider_wallet.address, "id": provider_wallet.id},
        ],
    )


# --- ERC-721 NFT Trade Methods ---

def create_nft_trade(buyer_wallet, seller_wallet, asset_id, price, margin, job_id):
    """Create a collateralized NFT trade."""
    print(f"\nCreating NFT trade: Buyer {buyer_wallet.address}, Seller {seller_wallet.address}, Asset ID {asset_id}, Price {price}, Margin {margin}")
    
    buyer_address = Web3.to_checksum_address(buyer_wallet.address)
    seller_address = Web3.to_checksum_address(seller_wallet.address)

    # Approve USDC for margin
    approve_data = usdc_contract.functions.approve(NFT_CONTRACT, int(margin)).build_transaction({'from': buyer_address})['data']
    approve_req = developer_controlled_wallets.CreateContractExecutionTransactionForDeveloperRequest.from_dict({
        "walletId": buyer_wallet.id, "contractAddress": USDC_ADDRESS, "callData": approve_data, "feeLevel": "MEDIUM"
    })
    approve_tx = transactions_api.create_developer_transaction_contract_execution(approve_req)
    wait_for_transaction(approve_tx.data.id, "approve USDC for NFT margin")
    print("USDC approved for NFT trade margin")

    # Create trade
    create_data = nft_contract.functions.createTrade(
        buyer_address, seller_address, int(asset_id), int(price), int(margin)
    ).build_transaction({'from': buyer_address})['data']
    create_req = developer_controlled_wallets.CreateContractExecutionTransactionForDeveloperRequest.from_dict({
        "walletId": buyer_wallet.id, "contractAddress": NFT_CONTRACT, "callData": create_data, "feeLevel": "MEDIUM"
    })
    create_tx = transactions_api.create_developer_transaction_contract_execution(create_req)
    wait_for_transaction(create_tx.data.id, "create NFT trade")
    print("NFT trade created")
    return 0  # Assuming trade ID 0

def adjust_nft_margin(trade_id, additional_margin, buyer_wallet, job_id):
    """Adjust margin for NFT trade."""
    print(f"Adjusting margin for NFT trade {trade_id} by {additional_margin}")
    
    buyer_address = Web3.to_checksum_address(buyer_wallet.address)
    adjust_data = nft_contract.functions.adjustMargin(int(trade_id), int(additional_margin)).build_transaction({'from': buyer_address})['data']
    adjust_req = developer_controlled_wallets.CreateContractExecutionTransactionForDeveloperRequest.from_dict({
        "walletId": buyer_wallet.id, "contractAddress": NFT_CONTRACT, "callData": adjust_data, "feeLevel": "MEDIUM"
    })
    adjust_tx = transactions_api.create_developer_transaction_contract_execution(adjust_req)
    wait_for_transaction(adjust_tx.data.id, "adjust NFT margin")
    print("NFT margin adjusted")

def execute_nft_trade(trade_id, buyer_wallet, job_id):
    """Execute NFT trade settlement."""
    print(f"Executing NFT trade {trade_id}")
    
    buyer_address = Web3.to_checksum_address(buyer_wallet.address)
    execute_data = nft_contract.functions.executeTrade(int(trade_id)).build_transaction({'from': buyer_address})['data']
    execute_req = developer_controlled_wallets.CreateContractExecutionTransactionForDeveloperRequest.from_dict({
        "walletId": buyer_wallet.id, "contractAddress": NFT_CONTRACT, "callData": execute_data, "feeLevel": "MEDIUM"
    })
    execute_tx = transactions_api.create_developer_transaction_contract_execution(execute_req)
    wait_for_transaction(execute_tx.data.id, "execute NFT trade")
    print("NFT trade executed")

def substitute_nft_collateral(trade_id, new_token_address, amount, buyer_wallet, job_id):
    """Substitute collateral in NFT trade."""
    print(f"Substituting collateral for NFT trade {trade_id} with {amount} of {new_token_address}")
    
    buyer_address = Web3.to_checksum_address(buyer_wallet.address)
    checksum_token = Web3.to_checksum_address(new_token_address)

    # Approve new token
    new_token_contract = web3.eth.contract(address=checksum_token, abi=ERC20_ABI)
    approve_data = new_token_contract.functions.approve(NFT_CONTRACT, int(amount)).build_transaction({'from': buyer_address})['data']
    approve_req = developer_controlled_wallets.CreateContractExecutionTransactionForDeveloperRequest.from_dict({
        "walletId": buyer_wallet.id, "contractAddress": checksum_token, "callData": approve_data, "feeLevel": "MEDIUM"
    })
    approve_tx = transactions_api.create_developer_transaction_contract_execution(approve_req)
    wait_for_transaction(approve_tx.data.id, "approve new token")
    print("New token approved")

    substitute_data = nft_contract.functions.substituteCollateral(int(trade_id), checksum_token, int(amount)).build_transaction({'from': buyer_address})['data']
    substitute_req = developer_controlled_wallets.CreateContractExecutionTransactionForDeveloperRequest.from_dict({
        "walletId": buyer_wallet.id, "contractAddress": NFT_CONTRACT, "callData": substitute_data, "feeLevel": "MEDIUM"
    })
    substitute_tx = transactions_api.create_developer_transaction_contract_execution(substitute_req)
    wait_for_transaction(substitute_tx.data.id, "substitute NFT collateral")
    print("NFT collateral substituted")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\nError: {error}")
        sys.exit(1)

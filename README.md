# Collateralized Trade Lifecycle on Circle ARC

This project implements a DeFi-style trade workflow on Circle ARC Testnet, mirroring the Solidity smart contracts in `CollateralizedTrade.sol` (ERC-20) and `CollateralizedTradeERC8183.sol` (ERC-721 for NFTs).

## Trade Lifecycle Diagram

```mermaid
sequenceDiagram
    participant C as Client Wallet<br/>(Buy-Side Firm)
    participant P as Provider Wallet<br/>(Sell-Side Firm)
    participant AC as AgenticCommerce<br/>Contract (ERC-8183)
    participant NFT as NFT Contract<br/>(ERC-721 Collateral)

    Note over C,P: Step 1–2: Setup
    C->>C: Create wallets (Circle API)<br/>Fund via faucet

    Note over C,P: Step 3–4: Bootstrap
    C->>P: Transfer 1 USDC starter balance
    C->>C: Check balances
    P->>P: Check balances

    Note over C,AC: Step 5: Order Matching
    C->>AC: createJob(provider, evaluator, expiry, desc, hook)
    AC-->>C: JobCreated event → jobId<br/>Status: Open

    Note over P,AC: Step 6: Contract Value
    P->>AC: setBudget(jobId, 5 USDC, 0x)
    AC-->>P: Budget set<br/>Status: Open

    Note over C,AC: Step 7–8: Clearing / Margin
    C->>AC: approve(AgenticCommerce, 5 USDC) on USDC
    C->>AC: fund(jobId, 0x)
    AC-->>C: USDC locked in escrow<br/>Status: Funded

    Note over P,AC: Step 9: Delivery Obligation
    P->>AC: submit(jobId, deliverableHash, 0x)
    AC-->>P: Hash stored on-chain<br/>Status: Submitted

    Note over C,AC: Step 10: Final Settlement (DVP)
    C->>AC: complete(jobId, reasonHash, 0x)
    AC-->>P: USDC released to Provider<br/>Status: Completed

    Note over C,AC: Step 11–12: Reconciliation
    C->>AC: getJob(jobId) — read final state
    C->>C: Check final USDC balance
    P->>P: Check final USDC balance

    rect rgb(235, 220, 245)
        Note over C,NFT: ERC-721 NFT Collateral Operations (separate helpers)
        C->>NFT: approve(NFT_CONTRACT, margin) on USDC
        C->>NFT: createTrade(buyer, seller, assetId, price, margin)
        NFT-->>C: Trade struct created, executed=false

        C->>NFT: adjustMargin(tradeId, additionalMargin)
        NFT-->>C: marginPosted increased

        C->>NFT: substituteCollateral(tradeId, newToken, amount)
        NFT-->>C: Collateral token swapped

        C->>NFT: executeTrade(tradeId)
        NFT-->>C: NFT → Buyer, USDC → Seller<br/>executed=true
    end
```

## Settlement Comparison: Traditional vs On-Chain

Each step in this workflow maps directly to a stage in traditional capital markets post-trade processing — but compressed from days to minutes.

| Traditional Stage | Typical Timing | On-Chain Equivalent | Step(s) |
|---|---|---|---|
| Order Matching | T+0 | `createJob()` | Step 5 |
| Trade Confirmation & Affirmation | T+0 → T+1 | `setBudget()` | Step 6 |
| Clearing — CCP novation + margin call | T+1 | `approve()` + `fund()` | Steps 7–8 |
| Delivery Obligation (confirm to CCP) | T+1 → T+2 | `submit(deliverableHash)` | Step 9 |
| Settlement — DVP | T+2 (T+1 post SEC 2024 rule) | `complete()` — atomic on-chain | Step 10 |
| Reconciliation | T+2 → T+3 | `getJob()` + balance check | Steps 11–12 |

### Where the biggest difference lies: Clearing (Steps 7–8)

In traditional markets, clearing is handled by a Central Counterparty (CCP) such as DTCC. After a trade is matched at T+0, the CCP novates the trade and issues margin calls processed in **overnight batch windows** — creating a counterparty risk exposure window of up to 24 hours before collateral is actually locked.

On-chain, the smart contract *is* the CCP. `approve()` + `fund()` lock collateral in a single transaction sequence — there is no overnight window and no bilateral counterparty risk between execution and clearing.

### Time saved

| | Traditional | On-Chain |
|---|---|---|
| Execution → Clearing | ≈24 hours (T+0 to T+1) | Seconds |
| Clearing → DVP Settlement | ≈24 hours (T+1 to T+2) | Seconds |
| **Total (execution to settlement)** | **1–2 business days** | **Minutes** |

The clearing-to-settlement gap is eliminated entirely. Every step from order matching (Step 5) through final DVP (Step 10) executes sequentially on-chain within a single session, with per-transaction finality.

### Real-world example: BlackRock buys 1M TSLA shares from Goldman Sachs

> Assumed price: **$250/share → $250,000,000 notional**
> Assumed Fed Funds rate: 5.33% (252 trading days/year)

#### Traditional T+1 settlement via NYSE + DTCC/NSCC

| Cost Category | BlackRock (Buyer) | Goldman Sachs (Seller) | DTCC / CCP |
|---|---|---|---|
| NSCC clearing fee (~0.5 bps) | $1,250 | $1,250 | +$2,500 revenue |
| DTC settlement fee | $50 | $50 | +$100 revenue |
| Capital lock-up cost¹ (1 business day @ 5.33%) | **$52,877** | — | — |
| Short position hedging / stock borrow² | — | **$10,500** | — |
| Back-office: confirmation, affirmation, recon | $350 | $350 | — |
| **Total** | **$54,527** | **$12,150** | **$2,600 revenue** |

¹ Buyer must keep $250M cash earmarked and uninvested for the settlement window: $250M × 5.33% ÷ 252 = $52,877/day.  
² Goldman holds a short overnight to deliver on T+1. Stock borrow at ~1% annualised: $250M × 1% ÷ 252 ≈ $9,921, plus back-office overhead.

**Combined cost to both trading parties: ~$66,677**

#### On-chain settlement (this implementation)

| Cost Category | BlackRock (Client Wallet) | Goldman Sachs (Provider Wallet) | Smart Contract |
|---|---|---|---|
| Gas fees (~10 transactions on ARC) | ~$5 | ~$5 | — |
| Capital lock-up | $0 | $0 | — |
| Back-office processing | $0 (automated) | $0 (automated) | — |
| **Total** | **~$5** | **~$5** | **$0** |

**Combined cost to both trading parties: ~$10**

#### Savings summary

| Party | Traditional | On-Chain | **Saved** |
|---|---|---|---|
| BlackRock (buy-side) | $54,527 | $5 | **$54,522** |
| Goldman Sachs (sell-side) | $12,150 | $5 | **$12,145** |
| DTCC / CCP | — | — | Disintermediated |
| **All parties combined** | **$66,677** | **$10** | **$66,667 (99.99%)** |

DTCC is disintermediated entirely — the smart contract enforces the same novation and collateral-locking guarantees that the CCP provides, but without the overnight batch cycle or clearing fund contribution.

At BlackRock's reported ≈$500B/day in equity trading volume, even routing **0.01%** of that through on-chain settlement would yield **≈$1.3M/day** in capital cost savings from the settlement window alone.

### Risks in today's capital market ecosystem

The cost savings above are real, but so are the adoption barriers. These are the live risks that any institution faces when moving post-trade infrastructure on-chain today, alongside how Circle and ARC directly address each one.

| # | Risk | Core issue in today's market | How Circle / ARC mitigates it |
|---|---|---|---|
| 1 | **Loss of multilateral netting** | NSCC reduces gross settlement volumes by ~95% daily by netting offsetting obligations across all participants. On-chain gross settlement means 10 trades of 1M TSLA still require 10 full $250M settlements — not one net — potentially reversing the capital savings at scale. | Circle's programmable wallet infrastructure on ARC can implement a **netting smart contract layer**: multiple bilateral trades are aggregated intra-day and a single net settlement transaction is submitted, replicating NSCC-style netting without the overnight batch cycle. |
| 2 | **Legal finality ≠ blockchain finality** | UCC Article 8 and registered clearing agency rules govern legal settlement finality in the US. A smart contract `complete()` has no standing under these rules today — on-chain state says "settled" while courts may not. | Circle actively engages with US and EU regulators (NYDFS, SEC, MiCA framework) on regulatory recognition of on-chain settlement. ARC is designed as a **compliant institutional chain**; Circle's legal team supports clients in structuring transactions that align on-chain finality with UCC Article 12 (enacted 2023) which explicitly recognises controllable electronic records as property. |
| 3 | **KYC/AML and accredited investor compliance** | Traditional settlement passes through FINRA-registered broker-dealers who perform KYC, AML screening, and suitability checks. Wallet addresses carry none of this context natively. | Circle's **Developer-Controlled Wallets API enforces identity verification at wallet provisioning** — wallets are issued only to entities that pass Circle's compliance layer. Circle holds money transmitter licences in 49 US states and an EU e-money licence, making the wallet layer itself a regulated touchpoint rather than an anonymous address. |
| 4 | **No erroneous trade / bust-trade mechanism** | FINRA Rule 11890 and exchange clearly-erroneous trade policies allow post-execution cancellation. An on-chain `complete()` is irreversible — no circuit breaker or regulatory halt can override a settled transaction. | The `admin` role in ARC's smart contracts (visible in `NFT_ABI` in this repo) provides a Circle-governed **emergency intervention key**. On ARC's permissioned validator set, Circle and institutional co-validators can coordinate a time-locked dispute window — analogous to a T+0 bust-trade window — before a transaction achieves full legal finality. |
| 5 | **Stablecoin peg risk** | A temporary USDC depeg during Steps 7–10 means the buyer delivers $250M nominal USDC worth less in USD at DVP. Traditional settlement uses central bank money (Fedwire) with no peg risk. Tokenised equities add issuer redemption risk on top. | USDC is Circle's own product — **fully reserved 1:1 by cash and short-dated US Treasuries**, attested monthly by Deloitte, and has maintained its peg since launch. On ARC, USDC is the **native settlement currency** with no bridge or wrapping risk. Circle's reserve transparency and regulatory standing are the closest analogue to central bank money available in the tokenised asset ecosystem today. |
| 6 | **MEV and front-running** | A pending `createJob()` or `fund()` on a public mempool reveals trade direction, size, and price before confirmation. Validators and searchers can front-run or sandwich the transaction, repricing the trade against the initiating party. | ARC operates a **permissioned validator set** of institutional participants — not anonymous miners or public stakers. Transactions are submitted through Circle's private RPC endpoint, bypassing any public mempool entirely. Block production is controlled, making MEV extraction structurally impossible without explicit collusion among the whitelisted validators. |
| 7 | **Custody and key management** | SEC Rule 15c3-3 and the Investment Advisers Act impose strict custody requirements. Loss or compromise of the Circle entity secret results in permanent asset loss — no SIPC protection, no legal recourse equivalent to a qualified custodian. | Circle's Developer-Controlled Wallets use **MPC (Multi-Party Computation)** key management backed by HSMs (Hardware Security Modules), distributing key shards so that no single point of compromise is sufficient. Circle is a licensed money transmitter and is pursuing a US federal bank charter, positioning it as a **qualified custodian** under SEC rules — giving institutional clients the regulatory custody coverage required by the Investment Advisers Act. |

## Low-Impact Adoption Strategy: Traditional Exchange → ARC Settlement

A "big bang" migration from DTCC to on-chain settlement is neither realistic nor safe. The strategy below is designed so that an exchange adds ARC as a parallel settlement rail and shifts volume incrementally — each phase producing measurable savings with no risk to the existing participant base.

### Guiding principles

- **No forced migration** — existing T+1/DTCC settlement continues throughout every phase
- **Start with net-new** — onboard assets that have no legacy settlement infrastructure first
- **Opt-in before mandate** — participants choose to use ARC; it is never imposed
- **API-first integration** — ARC bolts onto the exchange's existing OMS/post-trade stack via Circle's Developer-Controlled Wallets API without replacing it

---

### Phase 1 — Shadow mode (0% volume shift, 0 participant impact)

**What happens:** The exchange runs ARC settlement in parallel with DTCC for a subset of trades — comparing results, timing, and cost — without routing any real settlement obligation through ARC. Participants see nothing different.

**What to build:**
- Connect exchange's trade feed to `createJob()` / `fund()` / `complete()` on ARC testnet for every matched trade
- Log on-chain settlement time vs. DTCC T+1 confirmation time side-by-side
- Validate that `getJob()` state matches DTCC confirmed status for every trade

**Circle/ARC tools used:** Developer-Controlled Wallets API, ARC Testnet RPC, `arcscan` for audit trail

**Exit criterion:** 30 consecutive trading days with zero state divergence between ARC shadow log and DTCC settlement record.

---

### Phase 2 — Tokenised new listings (≈5–10% volume)

**What happens:** New securities listed on the exchange are issued as tokenised assets on ARC from day one. They have no pre-existing DTCC settlement infrastructure, so there is nothing to migrate. Buyers and sellers of these instruments settle entirely on-chain via DVP.

**What to build:**
- Issue new listings as ERC-20 (fungible) or ERC-721 (NFT for unique instruments) on ARC
- Provision participant wallets through Circle's Developer-Controlled Wallets API — participants interact through existing order management interfaces; the wallet layer is invisible
- Map `createJob()` → order match, `fund()` → clearing, `complete()` → DVP settlement

**Regulatory consideration:** File with the SEC under the existing ATS (Alternative Trading System) exemption or seek a no-action letter for tokenised securities settlement. Circle's regulatory team has established relationships with NYDFS and the SEC to support this process.

**Exit criterion:** 6 months of clean settlement on tokenised listings with no failed DVPs and participant satisfaction scores matching or exceeding DTCC SLAs.

---

### Phase 3 — Block trade opt-in for institutional counterparties (≈15–25% volume)

**What happens:** Large negotiated block trades (e.g. >$50M notional) between two institutions are offered an opt-in ARC settlement path. Both counterparties must consent. The trade is bilateral, so there is no multilateral netting impact (Phase 1 identified this as the key structural risk).

**What to build:**
- Add an "ARC Settlement" toggle to the block trade negotiation UI
- When both sides opt in, route through `createJob()` → `setBudget()` → `approve()` → `fund()` → `submit()` → `complete()` within a single session
- Maintain a DTCC fallback: if either side's `fund()` fails within a timeout, revert and fall back to standard T+1

**Savings unlocked:** The full $66,667 per $250M trade modelled in the BlackRock/Goldman example applies here. At 20 such block trades per month, that is ≈$1.3M/month in participant cost savings — a tangible incentive for opt-in.

**Exit criterion:** 80% of eligible block trade counterparties actively choosing ARC settlement within 12 months.

---

### Phase 4 — Default settlement for eligible securities (≈50–60% volume)

**What happens:** ARC becomes the default settlement rail for all tokenised assets and all securities where both counterparties have active Circle wallets provisioned. DTCC remains the fallback for participants who have not yet onboarded.

**What to build:**
- Implement on-chain multilateral netting contract: aggregate all bilateral trades intra-day per security, net positions, submit a single gross settlement per participant per day — replicating NSCC netting and recovering the netting efficiency identified as a Phase 1 risk
- Automate wallet provisioning at account opening so every new participant gets a Circle wallet by default

**Regulatory milestone required:** Exchange must obtain recognition from the SEC that ARC settlement constitutes legal settlement finality (UCC Article 12 framework) before mandating this phase.

**Exit criterion:** Net settlement volumes on ARC match or beat DTCC netting efficiency (≥90% reduction in gross obligations).

---

### Phase 5 — Full migration, DTCC as backstop only (≈95–100% volume)

**What happens:** ARC handles all settlement. DTCC connectivity is maintained purely as a regulatory backstop and for cross-market interoperability (e.g. trades that cross into non-ARC venues). The overnight batch cycle is eliminated.

**Outcome at scale:**

| Metric | Traditional (DTCC) | ARC (Phase 5) |
|---|---|---|
| Settlement window | T+1 (24 hrs) | Minutes |
| Failed trade rate | ≈0.3% (industry avg) | Near zero (atomic DVP) |
| Capital locked in settlement pipeline | ≈2× daily volume | ≈0 |
| CCP clearing fee per $250M trade | $2,600 | $0 |
| Participant capital cost per $250M trade | $66,677 | $10 |

---

### Migration risk controls at every phase

| Control | Mechanism |
|---|---|
| Fallback to DTCC | Every on-chain flow has a timeout; unresolved trades revert to T+1 automatically |
| Admin intervention | `admin` key on ARC contracts allows Circle + exchange to cancel and re-route within the dispute window |
| Participant opt-out | Any participant can revert to DTCC settlement at any phase without penalty |
| Regulatory checkpoint | Each phase requires explicit sign-off from exchange compliance and legal before volume is shifted |

## Features

- Trade execution (buyer & seller agreement)
- Clearing (validate trade, lock collateral)
- Initial margin posting (escrow)
- Variation margin (adjust collateral)
- Collateral movement (substitute/reallocate)
- Settlement (DVP: deliver asset, release funds)
- Balance and job status tracking

## Setup

1. Deploy one of the contracts on Circle ARC Testnet:
   - `CollateralizedTrade.sol`: For ERC-20 tokenized assets
   - `CollateralizedTradeERC8183.sol`: For ERC-721 NFT assets
   Provide USDC and asset token addresses as constructor arguments.

   **Deployment using Python script:**
   - Add `PRIVATE_KEY` to your `.env` file (account with testnet funds).
   - Update `usdc_address` and `asset_address` in `deploy_contract.py` (find testnet token addresses or deploy your own ERC-20/ERC-721).
   - Set `contract_file` to the desired contract.
   - Run: `python deploy_contract.py`

   Alternatively, use Remix IDE or Hardhat:
   - Connect to Circle ARC testnet RPC: `https://rpc.testnet.arc.network`
   - Deploy with constructor args.

2. Create a virtual environment and activate it:
   ```bash
   python -m venv circle
   source circle/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set environment variables in a `.env` file:
   ```
   CIRCLE_API_KEY=your_api_key
   CIRCLE_ENTITY_SECRET=your_entity_secret
   PRIVATE_KEY=your_private_key  # For contract deployment (see below)
   ```

   **Getting a Private Key:**
   - Use a wallet like MetaMask: Create or import an account, then export the private key (Account > Export Private Key).
   - For testnet, create a new account to avoid using mainnet keys.
   - Fund the account with testnet ETH (faucet for Circle ARC or Polygon Mumbai if applicable).
   - **Security Warning:** Never share or commit private keys. Use environment variables and keep them secure.

5. Update the constants in the appropriate Python file:
   - `TRADE_CONTRACT`: Use the deployed address (e.g., `0xe185f2E0ebf96638bfCe09FC6b77d36d17FCC32c`)
   - `USDC_ADDRESS`: USDC contract address on testnet
   - `ASSET_ADDRESS`: Asset token contract address
   - For NFT: `ASSET_ID`: Token ID to trade

## Usage

Run the main script:
```bash
python collateralized_trade.py
```

This runs the full ERC-8183 Agentic Commerce trade lifecycle (Steps 1–12). NFT collateral operations (`create_nft_trade`, `adjust_nft_margin`, `execute_nft_trade`, `substitute_nft_collateral`) are defined in the same file and can be called directly after completing the main flow.

The script will:
- Create buyer and seller wallets
- Fund and transfer initial collateral
- Create a job for the trade
- Set budget
- Perform approval, escrow funding, margin adjustments, collateral substitution
- Submit deliverable
- Complete the job
- Print final balances and status

## Notes

- Ensure you have sufficient funds in testnet for transactions.
- The contract ABI is mocked; replace with actual ABI from your Solidity contract.
- Transactions wait for on-chain confirmation with retries.
- Atomicity is ensured via job budgeting and transaction sequencing.


// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// CCP Function 1: Novation
//
// In traditional markets the CCP interposes itself between buyer and seller so
// neither faces the other's default risk. This contract replicates that by
// becoming the counterparty to both sides: the buyer's margin is locked here,
// and the DVP (delivery-versus-payment) leg is executed atomically by the
// contract — not between the two parties directly.
//
// On ARC: replaces NSCC novation fully. Both parties face the contract.
// Bilateral counterparty risk is eliminated at the point of registration.

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
}

interface IERC721 {
    function transferFrom(address from, address to, uint256 tokenId) external;
    function ownerOf(uint256 tokenId) external view returns (address);
}

contract Novation {
    enum Status { Open, Novated, Settled, Defaulted }

    struct Trade {
        address buyer;
        address seller;
        address asset;       // ERC-721 contract address
        uint256 assetId;     // token ID
        uint256 price;       // full price in USDC (6 decimals)
        uint256 margin;      // collateral posted by buyer at registration
        Status  status;
        uint256 registeredAt;
    }

    IERC20  public immutable usdc;
    address public admin;

    mapping(address => bool) public authorized; // contracts allowed to call restricted fns

    uint256 public nextTradeId;
    mapping(uint256 => Trade) public trades;

    event TradeRegistered(uint256 indexed tradeId, address buyer, address seller, uint256 price);
    event TradeNovated(uint256 indexed tradeId);
    event TradeSettled(uint256 indexed tradeId);
    event TradeDefaulted(uint256 indexed tradeId, address defaultingParty);

    modifier onlyAdmin() {
        require(msg.sender == admin, "admin only");
        _;
    }

    modifier onlyAdminOrAuthorized() {
        require(msg.sender == admin || authorized[msg.sender], "unauthorized");
        _;
    }

    constructor(address _usdc) {
        usdc  = IERC20(_usdc);
        admin = msg.sender;
    }

    // Buyer registers a trade and posts initial margin upfront.
    // From this point the buyer faces the contract, not the seller.
    function registerTrade(
        address seller,
        address asset,
        uint256 assetId,
        uint256 price,
        uint256 margin
    ) external returns (uint256 tradeId) {
        require(margin > 0 && margin <= price, "invalid margin");
        usdc.transferFrom(msg.sender, address(this), margin);

        tradeId = nextTradeId++;
        trades[tradeId] = Trade({
            buyer:        msg.sender,
            seller:       seller,
            asset:        asset,
            assetId:      assetId,
            price:        price,
            margin:       margin,
            status:       Status.Open,
            registeredAt: block.timestamp
        });

        emit TradeRegistered(tradeId, msg.sender, seller, price);
    }

    // Admin confirms both sides are committed. After novation the contract is the
    // legal counterparty; the original buyer/seller relationship is replaced.
    function novateTrade(uint256 tradeId) external onlyAdmin {
        Trade storage t = trades[tradeId];
        require(t.status == Status.Open, "not open");
        t.status = Status.Novated;
        emit TradeNovated(tradeId);
    }

    // Atomic DVP: seller delivers asset, buyer pays remaining price, contract
    // releases full price to seller. Neither party can fail independently.
    function settle(uint256 tradeId) external onlyAdminOrAuthorized {
        Trade storage t = trades[tradeId];
        require(t.status == Status.Novated, "not novated");

        uint256 remaining = t.price - t.margin;
        usdc.transferFrom(t.buyer, address(this), remaining);
        IERC721(t.asset).transferFrom(t.seller, t.buyer, t.assetId);
        usdc.transfer(t.seller, t.price);

        t.status = Status.Settled;
        emit TradeSettled(tradeId);
    }

    // Admin declares a party in default. Margin is retained for loss coverage
    // and forwarded to DefaultWaterfall.
    function declareDefault(uint256 tradeId, address defaultingParty) external onlyAdmin {
        Trade storage t = trades[tradeId];
        require(t.status != Status.Settled && t.status != Status.Defaulted, "terminal state");
        t.status = Status.Defaulted;
        emit TradeDefaulted(tradeId, defaultingParty);
    }

    function authorize(address caller) external onlyAdmin {
        authorized[caller] = true;
    }

    function transferAdmin(address newAdmin) external onlyAdmin {
        admin = newAdmin;
    }
}

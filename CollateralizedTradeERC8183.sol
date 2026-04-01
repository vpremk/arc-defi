// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

interface IERC721 {
    function transferFrom(address from, address to, uint256 tokenId) external;
    function ownerOf(uint256 tokenId) external view returns (address);
}

contract CollateralizedTradeERC8183 {
    address public admin;
    IERC20 public stablecoin;      // e.g., USDC
    IERC721 public assetToken;     // tokenized asset as NFT

    struct Trade {
        address buyer;
        address seller;
        uint256 assetId;           // NFT token ID
        uint256 price;             // total trade price
        uint256 marginPosted;      // collateral amount
        bool executed;
    }

    mapping(uint256 => Trade) public trades;
    uint256 public nextTradeId;

    constructor(address _stablecoin, address _assetToken) {
        admin = msg.sender;
        stablecoin = IERC20(_stablecoin);
        assetToken = IERC721(_assetToken);
    }

    // --- Clearing & Collateral Management ---

    function createTrade(address buyer, address seller, uint256 assetId, uint256 price, uint256 margin) external returns (uint256) {
        require(msg.sender == admin, "Only admin");
        require(stablecoin.balanceOf(buyer) >= margin, "Insufficient margin");
        require(assetToken.ownerOf(assetId) == seller, "Seller does not own the asset");

        // Lock initial margin
        stablecoin.transferFrom(buyer, address(this), margin);

        trades[nextTradeId] = Trade({
            buyer: buyer,
            seller: seller,
            assetId: assetId,
            price: price,
            marginPosted: margin,
            executed: false
        });

        nextTradeId++;
        return nextTradeId - 1;
    }

    // Adjust collateral (variation margin)
    function adjustMargin(uint256 tradeId, uint256 additionalMargin) external {
        Trade storage t = trades[tradeId];
        require(!t.executed, "Trade executed");
        require(msg.sender == t.buyer, "Only buyer");

        // Post additional collateral
        stablecoin.transferFrom(msg.sender, address(this), additionalMargin);
        t.marginPosted += additionalMargin;
    }

    // --- Settlement ---

    function executeTrade(uint256 tradeId) external {
        Trade storage t = trades[tradeId];
        require(!t.executed, "Already executed");
        require(t.marginPosted >= t.price, "Insufficient margin for settlement");

        // Atomic settlement
        assetToken.transferFrom(t.seller, t.buyer, t.assetId);

        // Release margin to seller
        stablecoin.transfer(t.seller, t.marginPosted);

        t.executed = true;
    }

    // Optional: Allow collateral substitution (swap one stablecoin for another)
    function substituteCollateral(uint256 tradeId, IERC20 newToken, uint256 amount) external {
        Trade storage t = trades[tradeId];
        require(!t.executed, "Trade executed");
        require(msg.sender == t.buyer, "Only buyer");

        // Release old margin
        stablecoin.transfer(t.buyer, t.marginPosted);

        // Lock new collateral
        newToken.transferFrom(msg.sender, address(this), amount);
        t.marginPosted = amount;
    }
}
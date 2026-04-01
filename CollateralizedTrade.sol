// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

contract CollateralizedTrade {
    address public admin;
    IERC20 public stablecoin;      // e.g., USDC
    IERC20 public assetToken;      // tokenized asset

    struct Trade {
        address buyer;
        address seller;
        uint256 assetAmount;
        uint256 price;             // total trade price
        uint256 marginPosted;      // collateral amount
        bool executed;
    }

    mapping(uint256 => Trade) public trades;
    uint256 public nextTradeId;

    constructor(address _stablecoin, address _assetToken) {
        admin = msg.sender;
        stablecoin = IERC20(_stablecoin);
        assetToken = IERC20(_assetToken);
    }

    // --- Clearing & Collateral Management ---

    function createTrade(address buyer, address seller, uint256 assetAmount, uint256 price, uint256 margin) external returns (uint256) {
        require(msg.sender == admin, "Only admin");
        require(stablecoin.balanceOf(buyer) >= margin, "Insufficient margin");
        require(assetToken.balanceOf(seller) >= assetAmount, "Seller has insufficient asset");

        // Lock initial margin
        stablecoin.transferFrom(buyer, address(this), margin);

        trades[nextTradeId] = Trade({
            buyer: buyer,
            seller: seller,
            assetAmount: assetAmount,
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
        require(
            assetToken.transferFrom(t.seller, t.buyer, t.assetAmount),
            "Asset transfer failed"
        );

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
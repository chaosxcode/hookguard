// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IHooks} from "v4-core/interfaces/IHooks.sol";

/* a long
   block comment
   that spans lines */
contract RiskyHook {
    mapping(PoolId => uint256) public accrued;

    function getHookPermissions() public pure returns (Permissions memory) {
        return Permissions({
            beforeInitialize: false,
            afterSwap: true,
            beforeSwap: true
        });
    }

    function beforeSwap(address, PoolKey calldata, SwapParams calldata, bytes calldata)
        external returns (bytes4, BeforeSwapDelta, uint24)
    {
        uint256 p = oracle.latestRoundData();
        return (IHooks.beforeSwap.selector, toBeforeSwapDelta(0,0), 0);
    }

    function afterSwap(address, PoolKey calldata, SwapParams calldata, BalanceDelta, bytes calldata)
        external returns (bytes4, int128)
    {
        IERC20(token).safeTransfer(msg.sender, 1);
        return (IHooks.afterSwap.selector, 0);
    }
}

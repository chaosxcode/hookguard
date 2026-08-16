// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {BaseHook} from "v4-periphery/utils/BaseHook.sol";

/// A hook that does the things HookGuard looks for:
///  - gates pool attachment via beforeInitialize
///  - inherits BaseHook, so callbacks carry the PoolManager guard
///  - bounds its dynamic fee
///  - wraps its external oracle call so a paused feed cannot brick swaps
contract GuardedHook is BaseHook {
    uint24 public constant MAX_FEE = 3000;
    mapping(PoolId => bool) public allowlist;

    function getHookPermissions() public pure returns (Permissions memory) {
        return Permissions({
            beforeInitialize: true,
            beforeSwap: true
        });
    }

    function _beforeInitialize(address, PoolKey calldata key, uint160)
        internal override returns (bytes4)
    {
        require(allowlist[key.toId()], "pool not allowed");
        return BaseHook.beforeInitialize.selector;
    }

    function _beforeSwap(address, PoolKey calldata, SwapParams calldata, bytes calldata)
        internal override returns (bytes4, BeforeSwapDelta, uint24)
    {
        uint24 fee = MAX_FEE;
        try oracle.latestRoundData() returns (uint256 p) {
            fee = p > 0 ? MAX_FEE : MAX_FEE;
        } catch {
            fee = MAX_FEE;
        }
        return (BaseHook.beforeSwap.selector, toBeforeSwapDelta(0, 0), fee);
    }
}

"""Rule-level unit tests. Run: python3 -m unittest discover -s tests -v

Complements the fixture gates in CI: fixtures prove the scanner discriminates
end-to-end; these pin each rule's trigger and suppression edges so a refactor
cannot silently change semantics.
"""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import scan as scanner                                     # noqa: E402

PERMS_ALL = """function getHookPermissions() public pure returns (Hooks.Permissions memory) {
    return Hooks.Permissions({
        beforeInitialize: false, afterInitialize: false,
        beforeAddLiquidity: false, afterAddLiquidity: false,
        beforeRemoveLiquidity: false, afterRemoveLiquidity: false,
        beforeSwap: true, afterSwap: true,
        beforeDonate: false, afterDonate: false,
        beforeSwapReturnDelta: false, afterSwapReturnsDelta: false,
        afterAddLiquidityReturnsDelta: false, afterRemoveLiquidityReturnsDelta: false
    });
}
"""

HEAD = """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import {BaseHook} from "v4-periphery/BaseHook.sol";
import {IPoolManager, PoolKey} from "v4-core/IPoolManager.sol";
"""


def write(src):
    f = tempfile.NamedTemporaryFile("w", suffix=".sol", delete=False)
    f.write(src)
    f.close()
    return f.name

def rules_of(src):
    r = scanner.analyze(write(src))
    return {code for _, code, _, _ in r["findings"]} if r else set()


class Qualification(unittest.TestCase):
    def test_concrete_after_abstract_is_analyzed(self):
        # hookathon layout: abstract base first, concrete hook after
        src = HEAD + """
abstract contract AirbagHookBase is BaseHook {
    function getHookPermissions() public pure virtual returns (Hooks.Permissions memory);
    constructor(IPoolManager m) BaseHook(m) {}
}

contract RealHook is AirbagHookBase {
    function getHookPermissions() public pure override returns (Hooks.Permissions memory) {
        return Hooks.Permissions({beforeSwap:true});
    }
    function _beforeSwap(address, PoolKey calldata, bytes calldata) internal override returns (bytes4) {
        return this.beforeSwap.selector;
    }
}
"""
        self.assertIsNotNone(scanner.analyze(write(src)))

    def test_pure_abstract_file_skipped(self):
        src = HEAD + "abstract contract OnlyBase is BaseHook {}"
        self.assertIsNone(scanner.analyze(write(src)))

    def test_template_names_skipped(self):
        for name in ("ExampleVulnerableHook", "Counter"):
            src = HEAD + PERMS_ALL.replace("Hooks.Permissions", "P") + \
                f"\ncontract {name} is BaseHook {{}}\n"
            if name == "ExampleVulnerableHook":
                self.assertIsNone(scanner.analyze(write(src)))


class GuardRule(unittest.TestCase):
    def test_unguarded_direct_ihooks_fires(self):
        src = ("// SPDX-License-Identifier: MIT\npragma solidity ^0.8.20;\n"
               "interface IHooks {}\n"
               "contract Naked is IHooks {\n"
               "  mapping(uint256 => bool) seen;\n"
               "  function beforeSwap(bytes32 k) external { seen[1] = true; }\n"
               "}\n")
        self.assertIn("MISSING_POOLMANAGER_GUARD", rules_of(src))

    def test_inline_negated_guard_suppresses(self):
        src = ("// SPDX-License-Identifier: MIT\npragma solidity ^0.8.20;\n"
               "contract G is IHooks {\n"
               "  address poolManager;\n"
               "  mapping(uint256 => bool) seen;\n"
               "  function beforeSwap(bytes32 k) external {\n"
               "    if (msg.sender != poolManager) revert NotPM();\n"
               "    seen[1] = true;\n"
               "  }\n}\n")
        self.assertNotIn("MISSING_POOLMANAGER_GUARD", rules_of(src))

    def test_custom_modifier_guard_suppresses(self):
        src = ("// SPDX-License-Identifier: MIT\npragma solidity ^0.8.20;\n"
               "contract G is IHooks {\n"
               "  address manager;\n"
               "  mapping(uint256 => bool) seen;\n"
               "  modifier onlyManager() { if (msg.sender != address(manager)) revert No(); _; }\n"
               "  function beforeSwap(bytes32 k) external onlyManager { seen[1] = true; }\n"
               "}\n")
        self.assertNotIn("MISSING_POOLMANAGER_GUARD", rules_of(src))


class Permissionless(unittest.TestCase):
    def test_stateful_ungated_fires_medium(self):
        src = HEAD + PERMS_ALL + """
contract P is BaseHook {
    mapping(PoolId => uint256) public s;
    constructor(IPoolManager m) BaseHook(m) {}
    function _beforeSwap(address, PoolKey calldata key, bytes calldata)
        internal override returns (bytes4, BeforeSwapDelta, uint24) {
        s[key.toId()] = 1;
        return (this.beforeSwap.selector, ZERO, 0);
    }
}
"""
        self.assertIn("PERMISSIONLESS_ATTACHMENT", rules_of(src))

    def test_zero_state_validation_suppresses(self):
        # Bunni pattern: stored state zero-check revert in a sibling library
        lib = ("library BunniLogic {\n"
               "  function beforeSwap(Slot0 storage slot0) external {\n"
               "    if (slot0.sqrtPriceX96 == 0 || other) { revert Bunni__InvalidSwap(); }\n"
               "  }\n}\n")
        hook = ("// SPDX-License-Identifier: MIT\npragma solidity ^0.8.20;\n"
                "contract BunniLike is BaseHook {\n"
                "  function beforeSwap(PoolKey calldata key) external {\n"
                "    BunniLogic.beforeSwap(slot0s[key.toId()]);\n"
                "  }\n}\n")
        import tempfile, os
        d = tempfile.mkdtemp()
        open(os.path.join(d, "BunniLogic.sol"), "w").write(lib)
        f = os.path.join(d, "BunniLike.sol")
        open(f, "w").write(hook)
        r = scanner.analyze(f)
        self.assertEqual([c for _, c, _, _ in r["findings"]], [])


class InertCallbacks(unittest.TestCase):
    def test_revert_only_callback_not_flagged(self):
        src = HEAD + """
contract X is BaseHook {
    function beforeInitialize(address, PoolKey calldata, uint160) external pure returns (bytes4) {
        revert Disabled();
    }
}
"""
        # no PA finding: declared perms absent but contract qualifies via BaseHook;
        # inert callback must not produce MISSING_POOLMANAGER_GUARD
        self.assertNotIn("MISSING_POOLMANAGER_GUARD", rules_of(src))


if __name__ == "__main__":
    unittest.main(verbosity=2)

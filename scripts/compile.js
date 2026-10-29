#!/usr/bin/env node
/**
 * 使用 solc 编译 EvidenceRegistry.sol，并输出 ABI + bytecode 到 artifacts。
 * 用法：npm run compile
 */
"use strict";

const fs = require("fs");
const path = require("path");
const solc = require("solc");

const ROOT = path.resolve(__dirname, "..");
const SOURCE_NAME = "contracts/EvidenceRegistry.sol";
const SOURCE_PATH = path.join(ROOT, SOURCE_NAME);
const OUTPUT_PATH = path.join(ROOT, "artifacts", "EvidenceRegistry.json");

const source = fs.readFileSync(SOURCE_PATH, "utf8");

const input = {
  language: "Solidity",
  sources: {
    [SOURCE_NAME]: { content: source },
  },
  settings: {
    optimizer: { enabled: true, runs: 200 },
    // 兼容 Ganache 7 默认 EVM 版本，避免新 opcode 导致的部署失败
    evmVersion: "paris",
    outputSelection: {
      "*": {
        "*": [
          "abi",
          "evm.bytecode.object",
          "evm.deployedBytecode.object",
          "metadata",
        ],
      },
    },
  },
};

console.log(`Compiling with solc ${solc.version()} ...`);
const output = JSON.parse(solc.compile(JSON.stringify(input)));

for (const item of output.errors || []) {
  const text = item.formattedMessage || item.message;
  if (item.severity === "error") {
    console.error(text);
  } else {
    console.warn(text);
  }
}

const errors = (output.errors || []).filter((e) => e.severity === "error");
if (errors.length > 0) {
  console.error(`\n编译失败：${errors.length} 个错误。`);
  process.exit(1);
}

const contract = output.contracts?.[SOURCE_NAME]?.EvidenceRegistry;
if (!contract) {
  console.error("编译成功但未找到 EvidenceRegistry 合约输出。");
  process.exit(1);
}

const artifact = {
  contractName: "EvidenceRegistry",
  sourceName: SOURCE_NAME,
  compiler: solc.version(),
  buildAt: new Date().toISOString(),
  abi: contract.abi,
  bytecode: `0x${contract.evm.bytecode.object}`,
  deployedBytecode: `0x${contract.evm.deployedBytecode.object}`,
};

fs.mkdirSync(path.dirname(OUTPUT_PATH), { recursive: true });
fs.writeFileSync(OUTPUT_PATH, `${JSON.stringify(artifact, null, 2)}\n`, "utf8");

const size = contract.evm.deployedBytecode.object.length / 2;
console.log(`\n编译成功：${OUTPUT_PATH}`);
console.log(`已部署字节码大小：${size} bytes`);

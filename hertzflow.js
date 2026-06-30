#!/usr/bin/env node
/**
 * HertzFlow Testnet Farming Bot (Node.js / ethers.js)
 * Mendukung: faucet, bind_reff, long, short, pool, vault, balance
 */

const { ethers } = require("ethers");
const fs = require("fs");
const readline = require("readline");

// ─── CONFIG ───────────────────────────────────────────────────────────────

const RPC_URL = "https://data-seed-prebsc-1-s1.bnbchain.org:8545";
const CHAIN_ID = 97;

const PRIVY_INIT_URL = "https://privy.hertzflow.xyz/api/v1/siwe/init";
const PRIVY_AUTH_URL = "https://privy.hertzflow.xyz/api/v1/siwe/authenticate";
const DATA_BASE_URL = "https://data-statistics-query.testnet.htzfl.link/api/v1/bsc";
const ORACLE_URL = "https://oracle-aggregator.hertzflow.xyz/api/v1/latestPrice?get_all=true";

const PRIVY_APP_ID = "cmh8y0unk02kdla0cvjk2uk8q";
const PRIVY_CA_ID = "eb833dff-2ede-4ed2-9061-85e4775514e7";

const USDT_CONTRACT = "0x6335881872FEcab922d1d83c6Bae6E27C5a9209c";
const REFF_CONTRACT = "0xB7812a1399FA6C9D40966F07F4B8f5C88A319F8D";
const ROUTER_CONTRACT = "0xc82ceF15311ff3B4a8ab576f43677662378D9F52";
const VAULT_ROUTER = "0x9A8958B6b3B945C71157E39DE969c95231F83181";

const POOL_FOREX = "0x07860Cc65deb99cb12d4582a7ae8123030c2d5C1"; // USD/TRY
const POOL_CRYPTO = "0x4cDe676F61dc2f85c83b9404833004b822721c0f"; // BTC/USD
const VAULT_POOL = "0x02Cf5deF6007e0e247a39571881eda95e0108B29"; // Tech Giants

const MARKETS = {
  "BTC/USD": "0xd537CD7D937446442c62B98c10a9c303152F289a",
};
const POOL_FOREX_MARKET = "0xaE2Ba965Cf653631737835c5679f6949D8DB3164";
const VAULT_MARKET = "0x79Bba0A9Ad45362404173E33d330c5eA6E02EE08";

let REFERRAL_CODE = "TENXZC";

const provider = new ethers.JsonRpcProvider(RPC_URL, CHAIN_ID);

const ERC20_ABI = [
  "function balanceOf(address) view returns (uint256)",
  "function allowance(address,address) view returns (uint256)",
  "function approve(address,uint256) returns (bool)",
  "function mint(address,uint256)",
];

// ─── UTILS ────────────────────────────────────────────────────────────────

function log(address, msg, status = "INFO") {
  const short = address.slice(0, 6) + "..." + address.slice(-4);
  const ts = new Date().toTimeString().split(" ")[0];
  console.log(`[${ts}] [${status}] ${short} | ${msg}`);
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function randRange(min, max) {
  return Math.random() * (max - min) + min;
}

function rl() {
  return readline.createInterface({ input: process.stdin, output: process.stdout });
}

function ask(question) {
  return new Promise((resolve) => {
    const i = rl();
    i.question(question, (ans) => {
      i.close();
      resolve(ans.trim());
    });
  });
}

function banner() {
  console.log(`
+------------------------------------------------+
|        HertzFlow Testnet Farming Bot           |
|             BSC Testnet (Chain 97)              |
+------------------------------------------------+
`);
}

function loadWallets(path = "wallets.txt") {
  if (!fs.existsSync(path)) {
    console.log(`[ERROR] File ${path} tidak ditemukan`);
    process.exit(1);
  }
  const lines = fs.readFileSync(path, "utf-8").split("\n");
  const wallets = [];
  for (let line of lines) {
    line = line.trim();
    if (!line || line.startsWith("#")) continue;
    try {
      const w = new ethers.Wallet(line, provider);
      wallets.push(w);
    } catch (e) {
      console.log(`[WARN] Private key invalid: ${line.slice(0, 10)}...`);
    }
  }
  return wallets;
}

// ─── SIWE AUTH ────────────────────────────────────────────────────────────

async function siweAuth(wallet) {
  const address = wallet.address;
  const headers = {
    "Content-Type": "application/json",
    Accept: "application/json",
    Origin: "https://testnet.hertzflow.xyz",
    Referer: "https://testnet.hertzflow.xyz/",
    "Privy-App-Id": PRIVY_APP_ID,
    "Privy-Ca-Id": PRIVY_CA_ID,
    "Privy-Client": "react-auth:3.27.0",
  };

  const initResp = await fetch(PRIVY_INIT_URL, {
    method: "POST",
    headers,
    body: JSON.stringify({ address }),
  });
  const initData = await initResp.json();
  const nonce = initData.nonce;

  const issuedAt = new Date().toISOString().replace(/\.\d+Z$/, ".000Z");
  const message =
    `testnet.hertzflow.xyz wants you to sign in with your Ethereum account:\n` +
    `${address}\n\n` +
    `By signing, you are proving you own this wallet and logging in. ` +
    `This does not initiate a transaction or cost any fees.\n\n` +
    `URI: https://testnet.hertzflow.xyz\n` +
    `Version: 1\n` +
    `Chain ID: 8453\n` +
    `Nonce: ${nonce}\n` +
    `Issued At: ${issuedAt}\n` +
    `Resources:\n` +
    `- https://privy.io`;

  const signature = await wallet.signMessage(message);

  const authPayload = {
    message,
    signature,
    chainId: "eip155:8453",
    connectorType: "injected",
    mode: "login-or-sign-up",
    walletClientType: "metamask",
  };

  const authResp = await fetch(PRIVY_AUTH_URL, {
    method: "POST",
    headers,
    body: JSON.stringify(authPayload),
  });
  const authData = await authResp.json();
  return authData.token || "";
}

// ─── FAUCET ───────────────────────────────────────────────────────────────

async function doFaucet(wallet) {
  const address = wallet.address;
  const contract = new ethers.Contract(USDT_CONTRACT, ERC20_ABI, wallet);
  const amount = ethers.parseUnits("100", 18);

  try {
    const tx = await contract.mint(address, amount);
    log(address, `Faucet tx: ${tx.hash}`);
    const receipt = await tx.wait();
    if (receipt.status === 1) {
      log(address, "Faucet SUCCESS - dapat 100 USDT", "OK");
      return true;
    } else {
      log(address, "Faucet FAILED", "ERR");
      return false;
    }
  } catch (e) {
    log(address, `Faucet error: ${e.message}`, "ERR");
    return false;
  }
}

// ─── BIND REFERRAL ────────────────────────────────────────────────────────

async function doBindReff(wallet, reffCode = REFERRAL_CODE) {
  const address = wallet.address;

  try {
    const resp = await fetch(
      `${DATA_BASE_URL}/user/referral-profile?user_address=${address}`
    );
    const json = await resp.json();
    const data = json.data || {};
    if (data.has_bound_referrer) {
      log(address, `Sudah bind reff: ${data.bound_referral_code}`, "SKIP");
      return true;
    }
  } catch (e) {
    log(address, `Gagal cek referral profile: ${e.message}`, "WARN");
  }

  // bindReferrer(bytes32 _code) - 0x65a46af4
  const codeBytes32 = ethers.encodeBytes32String(reffCode);
  const iface = new ethers.Interface(["function bindReferrer(bytes32)"]);
  const data = iface.encodeFunctionData("bindReferrer", [codeBytes32]);

  try {
    const tx = await wallet.sendTransaction({
      to: REFF_CONTRACT,
      data,
      gasLimit: 150000,
    });
    log(address, `Bind reff tx: ${tx.hash}`);
    const receipt = await tx.wait();
    if (receipt.status === 1) {
      log(address, `Bind reff SUCCESS - code: ${reffCode}`, "OK");
      return true;
    } else {
      log(address, "Bind reff FAILED", "ERR");
      return false;
    }
  } catch (e) {
    log(address, `Bind reff error: ${e.message}`, "ERR");
    return false;
  }
}

// ─── APPROVE USDT ─────────────────────────────────────────────────────────

async function approveUsdt(wallet, spender, amountWei) {
  const address = wallet.address;
  const contract = new ethers.Contract(USDT_CONTRACT, ERC20_ABI, wallet);

  try {
    const allowance = await contract.allowance(address, spender);
    if (allowance >= amountWei) return true;

    const maxAmount = ethers.MaxUint256;
    const tx = await contract.approve(spender, maxAmount);
    const receipt = await tx.wait();
    log(address, `Approve USDT tx: ${tx.hash} | status: ${receipt.status === 1 ? "OK" : "FAIL"}`);
    return receipt.status === 1;
  } catch (e) {
    log(address, `Approve error: ${e.message}`, "ERR");
    return false;
  }
}

// ─── ORACLE PRICE ─────────────────────────────────────────────────────────

async function getBtcPrice() {
  try {
    const resp = await fetch(ORACLE_URL);
    const data = await resp.json();
    let prices = data;
    if (data.data) prices = data.data;

    if (Array.isArray(prices)) {
      for (const p of prices) {
        const sym = p.token_symbol || p.symbol || "";
        if (String(sym).toUpperCase().includes("BTC")) {
          return {
            min: BigInt(p.min_price || p.price || 0),
            max: BigInt(p.max_price || p.price || 0),
          };
        }
      }
    } else if (typeof prices === "object") {
      for (const k in prices) {
        if (k.toUpperCase().includes("BTC")) {
          const v = prices[k];
          return {
            min: BigInt(v.min || v.price || 0),
            max: BigInt(v.max || v.price || 0),
          };
        }
      }
    }
  } catch (e) {
    console.log(`[WARN] Gagal fetch price: ${e.message}`);
  }
  // fallback
  const fallback = 60000n * 10n ** 12n;
  return { min: fallback, max: (fallback * 1001n) / 1000n };
}

// ─── LONG / SHORT (multicall) ──────────────────────────────────────────────
// CATATAN: struct createOrder direkonstruksi dari pola tx, belum 100% exact match.
// Kalau revert, perlu re-verify offset struct dari raw input data tx asli.

const ROUTER_IFACE = new ethers.Interface([
  "function multicall(bytes[] data) payable returns (bytes[])",
  "function sendWnt(address receiver, uint256 amount) payable",
  "function sendTokens(address token, address receiver, uint256 amount)",
  "function createOrder((bytes32 referralCode,(address receiver,address callbackContract,address uiFeeReceiver,address market,address initialCollateralToken,address[] swapPath) addresses,(uint256 sizeDeltaUsd,uint256 initialCollateralDeltaAmount,uint256 triggerPrice,uint256 acceptablePrice,uint256 executionFee,uint256 callbackGasLimit,uint256 minOutputAmount,uint256 validFromTime) numbers,uint8 orderType,uint8 decreasePositionSwapType,bool isLong,bool shouldUnwrapNativeToken,bool autoCancel) params) payable returns (bytes32)",
]);

async function doLongShort(wallet, isLong, amountUsdt) {
  const address = wallet.address;
  const dirLabel = isLong ? "LONG" : "SHORT";
  log(address, `Open ${dirLabel} BTC/USD | amount: ${amountUsdt} USDT`);

  const { min, max } = await getBtcPrice();
  if (min === 0n) {
    log(address, "Gagal dapat harga BTC", "ERR");
    return false;
  }

  const collateralWei = ethers.parseUnits(amountUsdt.toString(), 18);
  const marketAddr = MARKETS["BTC/USD"];
  const execFee = ethers.parseEther("0.006");

  await approveUsdt(wallet, ROUTER_CONTRACT, collateralWei * 2n);

  const leverageFactor = 11n; // 1.1x
  let sizeInUsd = (collateralWei * min * leverageFactor) / (10n * 10n ** 18n);
  if (sizeInUsd === 0n) sizeInUsd = (collateralWei * 110n) / 100n;

  const acceptablePrice = isLong
    ? (min * 99n) / 100n
    : (max * 101n) / 100n;

  const orderParams = {
    referralCode: ethers.encodeBytes32String(REFERRAL_CODE),
    addresses: {
      receiver: address,
      callbackContract: ethers.ZeroAddress,
      uiFeeReceiver: ethers.ZeroAddress,
      market: marketAddr,
      initialCollateralToken: USDT_CONTRACT,
      swapPath: [],
    },
    numbers: {
      sizeDeltaUsd: sizeInUsd,
      initialCollateralDeltaAmount: collateralWei,
      triggerPrice: 0n,
      acceptablePrice,
      executionFee: execFee,
      callbackGasLimit: 0n,
      minOutputAmount: 0n,
      validFromTime: 0n,
    },
    orderType: 2, // Market
    decreasePositionSwapType: 0,
    isLong,
    shouldUnwrapNativeToken: false,
    autoCancel: false,
  };

  const wrapData = ROUTER_IFACE.encodeFunctionData("sendWnt", [marketAddr, execFee]);
  const sendData = ROUTER_IFACE.encodeFunctionData("sendTokens", [USDT_CONTRACT, marketAddr, collateralWei]);
  const createData = ROUTER_IFACE.encodeFunctionData("createOrder", [orderParams]);

  const multicallData = ROUTER_IFACE.encodeFunctionData("multicall", [[wrapData, sendData, createData]]);

  try {
    const tx = await wallet.sendTransaction({
      to: ROUTER_CONTRACT,
      data: multicallData,
      value: execFee,
      gasLimit: 2000000,
    });
    log(address, `${dirLabel} tx: ${tx.hash}`);
    const receipt = await tx.wait();
    if (receipt.status === 1) {
      log(address, `${dirLabel} SUCCESS | ${amountUsdt} USDT`, "OK");
      return true;
    } else {
      log(address, `${dirLabel} FAILED`, "ERR");
      return false;
    }
  } catch (e) {
    log(address, `${dirLabel} error: ${e.message}`, "ERR");
    return false;
  }
}

// ─── POOL (multicall) ───────────────────────────────────────────────────────

const POOL_IFACE = new ethers.Interface([
  "function multicall(bytes[] data) payable returns (bytes[])",
  "function sendWnt(address receiver, uint256 amount) payable",
  "function sendTokens(address token, address receiver, uint256 amount)",
  "function createDeposit((address receiver,address callbackContract,address uiFeeReceiver,address market,address initialLongToken,address initialShortToken,address[] longTokenSwapPath,address[] shortTokenSwapPath) addresses,uint256 minMarketTokens,bool shouldUnwrapNativeToken,uint256 executionFee,uint256 callbackGasLimit) params) payable returns (bytes32)",
]);

async function doPool(wallet, amountUsdt, poolType) {
  const address = wallet.address;
  const poolAddr = poolType === "forex" ? POOL_FOREX : POOL_CRYPTO;
  const poolName = poolType === "forex" ? "USD/TRY (Forex)" : "BTC/USD (Crypto)";
  const marketAddr = poolType === "forex" ? POOL_FOREX_MARKET : MARKETS["BTC/USD"];

  log(address, `Add Liquidity Pool ${poolName} | ${amountUsdt} USDT`);

  const amountWei = ethers.parseUnits(amountUsdt.toString(), 18);
  const execFee = ethers.parseEther("0.006");

  await approveUsdt(wallet, ROUTER_CONTRACT, amountWei * 2n);

  const depositParams = {
    receiver: address,
    callbackContract: ethers.ZeroAddress,
    uiFeeReceiver: ethers.ZeroAddress,
    market: marketAddr,
    initialLongToken: USDT_CONTRACT,
    initialShortToken: USDT_CONTRACT,
    longTokenSwapPath: [],
    shortTokenSwapPath: [],
  };

  const wrapData = POOL_IFACE.encodeFunctionData("sendWnt", [poolAddr, execFee]);
  const sendData = POOL_IFACE.encodeFunctionData("sendTokens", [USDT_CONTRACT, poolAddr, amountWei]);
  const createData = POOL_IFACE.encodeFunctionData("createDeposit", [
    [depositParams, 0n, false, execFee, 0n],
  ]);

  const multicallData = POOL_IFACE.encodeFunctionData("multicall", [[wrapData, sendData, createData]]);

  try {
    const tx = await wallet.sendTransaction({
      to: ROUTER_CONTRACT,
      data: multicallData,
      value: execFee,
      gasLimit: 2000000,
    });
    log(address, `Pool tx: ${tx.hash}`);
    const receipt = await tx.wait();
    if (receipt.status === 1) {
      log(address, `Pool SUCCESS | ${amountUsdt} USDT ke ${poolName}`, "OK");
      return true;
    } else {
      log(address, "Pool FAILED", "ERR");
      return false;
    }
  } catch (e) {
    log(address, `Pool error: ${e.message}`, "ERR");
    return false;
  }
}

// ─── VAULT (multicall) ─────────────────────────────────────────────────────

const VAULT_IFACE = new ethers.Interface([
  "function multicall(bytes[] data) payable returns (bytes[])",
  "function sendWnt(address receiver, uint256 amount) payable",
  "function sendTokens(address token, address receiver, uint256 amount)",
  "function createDeposit((address receiver,address callbackContract,address uiFeeReceiver,address market,address initialLongToken,address initialShortToken,address[] longTokenSwapPath,address[] shortTokenSwapPath) addresses,uint256 minMarketTokens,bool shouldUnwrapNativeToken,uint256 executionFee,uint256 callbackGasLimit) params) payable returns (bytes32)",
]);

async function doVault(wallet, amountUsdt) {
  const address = wallet.address;
  log(address, `Deposit Vault Tech Giants | ${amountUsdt} USDT`);

  const amountWei = ethers.parseUnits(amountUsdt.toString(), 18);
  const execFee = ethers.parseEther("0.008");

  await approveUsdt(wallet, VAULT_ROUTER, amountWei * 2n);

  const depositParams = {
    receiver: address,
    callbackContract: ethers.ZeroAddress,
    uiFeeReceiver: ethers.ZeroAddress,
    market: VAULT_MARKET,
    initialLongToken: USDT_CONTRACT,
    initialShortToken: USDT_CONTRACT,
    longTokenSwapPath: [],
    shortTokenSwapPath: [],
  };

  const wrapData = VAULT_IFACE.encodeFunctionData("sendWnt", [VAULT_POOL, execFee]);
  const sendData = VAULT_IFACE.encodeFunctionData("sendTokens", [USDT_CONTRACT, VAULT_POOL, amountWei]);
  const createData = VAULT_IFACE.encodeFunctionData("createDeposit", [
    [depositParams, 0n, false, execFee, 0n],
  ]);

  const multicallData = VAULT_IFACE.encodeFunctionData("multicall", [[wrapData, sendData, createData]]);

  try {
    const tx = await wallet.sendTransaction({
      to: VAULT_ROUTER,
      data: multicallData,
      value: execFee,
      gasLimit: 2000000,
    });
    log(address, `Vault tx: ${tx.hash}`);
    const receipt = await tx.wait();
    if (receipt.status === 1) {
      log(address, `Vault SUCCESS | ${amountUsdt} USDT`, "OK");
      return true;
    } else {
      log(address, "Vault FAILED", "ERR");
      return false;
    }
  } catch (e) {
    log(address, `Vault error: ${e.message}`, "ERR");
    return false;
  }
}

// ─── BALANCE ──────────────────────────────────────────────────────────────

async function doBalance(wallet) {
  const address = wallet.address;
  const short = address.slice(0, 6) + "..." + address.slice(-4);

  const contract = new ethers.Contract(USDT_CONTRACT, ERC20_ABI, provider);
  const usdtBal = await contract.balanceOf(address);
  const bnbBal = await provider.getBalance(address);

  let vaultData = {};
  try {
    const resp = await fetch(`${DATA_BASE_URL}/vaults?wallet_address=${address}`);
    const json = await resp.json();
    vaultData = json.data || {};
  } catch (e) {}

  let activities = [];
  try {
    const resp2 = await fetch(`${DATA_BASE_URL}/user/activities?account=${address}&limit=20`);
    const json2 = await resp2.json();
    activities = (json2.data && json2.data.activities) || [];
  } catch (e) {}

  console.log(`\n+--- Balance: ${short} ---+`);
  console.log(`  BNB  : ${ethers.formatEther(bnbBal)}`);
  console.log(`  USDT : ${ethers.formatUnits(usdtBal, 18)}`);

  if (vaultData && Object.keys(vaultData).length > 0) {
    console.log(`\n  Vault/Pool Info:`);
    if (Array.isArray(vaultData)) {
      vaultData.forEach((item) => {
        console.log(`    ${item.symbol || "?"}: ${item.usd_value || 0} USD`);
      });
    } else {
      for (const k in vaultData) {
        if (k.toLowerCase().includes("usd") || k.toLowerCase().includes("share") || k.toLowerCase().includes("value")) {
          console.log(`    ${k}: ${vaultData[k]}`);
        }
      }
    }
  }

  for (const act of activities) {
    if (act.action_type === "trade") {
      const direction = act.direction || "?";
      const market = act.market_symbol || "?";
      const action = act.action || "?";
      const size = Number(act.size_in_usd || 0) / 10 ** 30;
      console.log(`  Trade: ${action} ${direction.toUpperCase()} ${market} | size: $${size.toFixed(2)}`);
    }
  }
  console.log("+----------------------------+\n");
}

// ─── MAIN FLOW ────────────────────────────────────────────────────────────

async function selectAccounts(wallets) {
  console.log(`Total akun: ${wallets.length}`);
  console.log("Pilih akun:");
  console.log("  1. Satu akun (pilih nomor)");
  console.log("  2. Semua akun");
  console.log("  3. From X to end");
  const choice = await ask("Pilihan (1/2/3): ");

  if (choice === "1") {
    wallets.forEach((w, i) => console.log(`  [${i + 1}] ${w.address}`));
    const idx = parseInt(await ask("Nomor akun: ")) - 1;
    return [wallets[idx]];
  } else if (choice === "2") {
    return wallets;
  } else if (choice === "3") {
    const start = parseInt(await ask("From index (1-based): ")) - 1;
    return wallets.slice(start);
  } else {
    console.log("Input invalid");
    process.exit(1);
  }
}

async function selectMode() {
  console.log("\nPilih mode:");
  console.log("  1. all      (faucet + bind reff + long + short + pool + vault)");
  console.log("  2. faucet");
  console.log("  3. bind_reff");
  console.log("  4. long");
  console.log("  5. short");
  console.log("  6. pool");
  console.log("  7. vault");
  console.log("  8. balance");
  const choice = await ask("Pilihan (1-8): ");
  const modes = {
    1: "all", 2: "faucet", 3: "bind_reff",
    4: "long", 5: "short", 6: "pool",
    7: "vault", 8: "balance",
  };
  return modes[choice] || "balance";
}

async function runWallet(wallet, mode) {
  const address = wallet.address;

  if (mode === "balance") {
    await doBalance(wallet);
    return;
  }

  if (mode === "faucet" || mode === "all") {
    log(address, "=== FAUCET ===");
    await doFaucet(wallet);
    await sleep(3000);
  }

  if (mode === "bind_reff" || mode === "all") {
    log(address, "=== BIND REFERRAL ===");
    await doBindReff(wallet);
    await sleep(3000);
  }

  if (mode === "long" || mode === "all") {
    log(address, "=== LONG ===");
    await doLongShort(wallet, true, Math.round(randRange(5, 15) * 100) / 100);
    await sleep(5000);
  }

  if (mode === "short" || mode === "all") {
    log(address, "=== SHORT ===");
    await doLongShort(wallet, false, Math.round(randRange(5, 15) * 100) / 100);
    await sleep(5000);
  }

  if (mode === "pool" || mode === "all") {
    log(address, "=== POOL ===");
    const poolType = Math.random() < 0.5 ? "forex" : "crypto";
    await doPool(wallet, Math.round(randRange(10, 25) * 100) / 100, poolType);
    await sleep(5000);
  }

  if (mode === "vault" || mode === "all") {
    log(address, "=== VAULT ===");
    await doVault(wallet, Math.round(randRange(10, 30) * 100) / 100);
    await sleep(3000);
  }
}

async function main() {
  banner();

  const wallets = loadWallets("wallets.txt");
  if (wallets.length === 0) {
    console.log("[ERROR] Tidak ada wallet ditemukan");
    process.exit(1);
  }

  const selected = await selectAccounts(wallets);
  const mode = await selectMode();

  console.log(`\nMode: ${mode.toUpperCase()} | Akun: ${selected.length}`);
  console.log("-".repeat(50));

  for (let i = 0; i < selected.length; i++) {
    const wallet = selected[i];
    console.log(`\n[${i + 1}/${selected.length}] Processing ${wallet.address}`);
    try {
      await runWallet(wallet, mode);
    } catch (e) {
      log(wallet.address, `Error: ${e.message}`, "ERR");
      console.error(e);
    }

    if (i < selected.length - 1) {
      const delay = Math.floor(randRange(5, 15)) * 1000;
      console.log(`Delay ${delay / 1000}s sebelum akun berikutnya...`);
      await sleep(delay);
    }
  }

  console.log("\n+--- SELESAI ---+");
}

main();

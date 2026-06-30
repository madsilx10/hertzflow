#!/usr/bin/env python3
"""
HertzFlow Testnet Farming Bot
Mendukung: faucet, bind reff, long, short, pool, vault, balance
"""

import os
import sys
import json
import time
import random
import struct
import hashlib
import requests
from datetime import datetime, timezone
from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

# ─── CONFIG ───────────────────────────────────────────────────────────────────

RPC_URL     = "https://data-seed-prebsc-1-s1.bnbchain.org:8545"
CHAIN_ID    = 97  # BSC Testnet

PRIVY_INIT_URL  = "https://privy.hertzflow.xyz/api/v1/siwe/init"
PRIVY_AUTH_URL  = "https://privy.hertzflow.xyz/api/v1/siwe/authenticate"
DATA_BASE_URL   = "https://data-statistics-query.testnet.htzfl.link/api/v1/bsc"
ORACLE_URL      = "https://oracle-aggregator.hertzflow.xyz/api/v1/latestPrice?get_all=true"

PRIVY_APP_ID    = "cmh8y0unk02kdla0cvjk2uk8q"
PRIVY_CA_ID     = "eb833dff-2ede-4ed2-9061-85e4775514e7"

# Contract addresses
USDT_CONTRACT   = Web3.to_checksum_address("0x6335881872FEcab922d1d83c6Bae6E27C5a9209c")
REFF_CONTRACT   = Web3.to_checksum_address("0xB7812a1399FA6C9D40966F07F4B8f5C88A319F8D")
ROUTER_CONTRACT = Web3.to_checksum_address("0xc82ceF15311ff3B4a8ab576f43677662378D9F52")
VAULT_ROUTER    = Web3.to_checksum_address("0x9A8958B6b3B945C71157E39DE969c95231F83181")
WBNB_CONTRACT   = Web3.to_checksum_address("0xae13d989dac2f0debff460ac112a837c89baa7cd")

# Pool addresses
POOL_FOREX      = Web3.to_checksum_address("0x07860Cc65deb99cb12d4582a7ae8123030c2d5C1")  # USD/TRY
POOL_CRYPTO     = Web3.to_checksum_address("0x4cDe676F61dc2f85c83b9404833004b822721c0f")  # BTC/USD
VAULT_POOL      = Web3.to_checksum_address("0x02Cf5deF6007e0e247a39571881eda95e0108B29")  # Tech Giants

# Market addresses (untuk trading)
MARKETS = {
    "BTC/USD": "0xd537CD7D937446442c62B98c10a9c303152F289a",
    "ETH/USD": None,  # tambah kalau ada
}

REFERRAL_CODE = "TENXZC"

w3 = Web3(Web3.HTTPProvider(RPC_URL))

# ─── BANNER ───────────────────────────────────────────────────────────────────

def banner():
    print("""
+------------------------------------------------+
|        HertzFlow Testnet Farming Bot           |
|             BSC Testnet (Chain 97)             |
+------------------------------------------------+
""")

# ─── UTILS ────────────────────────────────────────────────────────────────────

def load_wallets(path="wallets.txt"):
    if not os.path.exists(path):
        print(f"[ERROR] File {path} tidak ditemukan")
        sys.exit(1)
    wallets = []
    with open(path) as f:
        for line in f:
            pk = line.strip()
            if pk and not pk.startswith("#"):
                try:
                    acc = Account.from_key(pk)
                    wallets.append({"pk": pk, "address": acc.address})
                except Exception as e:
                    print(f"[WARN] Private key invalid: {pk[:10]}... ({e})")
    return wallets

def select_accounts(wallets):
    print(f"Total akun: {len(wallets)}")
    print("Pilih akun:")
    print("  1. Satu akun (pilih nomor)")
    print("  2. Semua akun")
    print("  3. From X to end")
    choice = input("Pilihan (1/2/3): ").strip()

    if choice == "1":
        for i, w in enumerate(wallets):
            print(f"  [{i+1}] {w['address']}")
        idx = int(input("Nomor akun: ")) - 1
        return [wallets[idx]]
    elif choice == "2":
        return wallets
    elif choice == "3":
        start = int(input("From index (1-based): ")) - 1
        return wallets[start:]
    else:
        print("Input invalid")
        sys.exit(1)

def select_mode():
    print("\nPilih mode:")
    print("  1. all      (faucet + bind reff + long + short + pool + vault)")
    print("  2. faucet")
    print("  3. bind_reff")
    print("  4. long")
    print("  5. short")
    print("  6. pool")
    print("  7. vault")
    print("  8. balance")
    choice = input("Pilihan (1-8): ").strip()
    modes = {
        "1": "all", "2": "faucet", "3": "bind_reff",
        "4": "long", "5": "short", "6": "pool",
        "7": "vault", "8": "balance"
    }
    return modes.get(choice, "balance")

def log(address, msg, status="INFO"):
    addr_short = address[:6] + "..." + address[-4:]
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{status}] {addr_short} | {msg}")

def wei_to_usdt(amount_wei, decimals=18):
    return amount_wei / (10 ** decimals)

def usdt_to_wei(amount, decimals=18):
    return int(amount * (10 ** decimals))

def bnb_to_wei(amount):
    return int(amount * 10**18)

# ─── SIWE AUTH ────────────────────────────────────────────────────────────────

def siwe_auth(wallet):
    address = wallet["address"]
    pk = wallet["pk"]

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": "https://testnet.hertzflow.xyz",
        "Referer": "https://testnet.hertzflow.xyz/",
        "Privy-App-Id": PRIVY_APP_ID,
        "Privy-Ca-Id": PRIVY_CA_ID,
        "Privy-Client": "react-auth:3.27.0",
    }

    # 1. Init - dapat nonce
    resp = requests.post(PRIVY_INIT_URL, json={"address": address}, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    nonce = data["nonce"]

    # 2. Build SIWE message
    issued_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    message = (
        f"testnet.hertzflow.xyz wants you to sign in with your Ethereum account:\n"
        f"{address}\n\n"
        f"By signing, you are proving you own this wallet and logging in. "
        f"This does not initiate a transaction or cost any fees.\n\n"
        f"URI: https://testnet.hertzflow.xyz\n"
        f"Version: 1\n"
        f"Chain ID: 8453\n"
        f"Nonce: {nonce}\n"
        f"Issued At: {issued_at}\n"
        f"Resources:\n"
        f"- https://privy.io"
    )

    # 3. Sign
    msg = encode_defunct(text=message)
    signed = Account.sign_message(msg, private_key=pk)
    signature = signed.signature.hex()
    if not signature.startswith("0x"):
        signature = "0x" + signature

    # 4. Authenticate
    auth_payload = {
        "message": message,
        "signature": signature,
        "chainId": "eip155:8453",
        "connectorType": "injected",
        "mode": "login-or-sign-up",
        "walletClientType": "metamask",
    }
    resp2 = requests.post(PRIVY_AUTH_URL, json=auth_payload, headers=headers, timeout=30)
    resp2.raise_for_status()
    auth_data = resp2.json()
    token = auth_data.get("token", "")
    return token

# ─── FAUCET ───────────────────────────────────────────────────────────────────

def do_faucet(wallet):
    address = wallet["address"]
    pk = wallet["pk"]

    # mint(address account, uint256 amount) - 100 USDT
    amount = usdt_to_wei(100)
    selector = bytes.fromhex("40c10f19")
    addr_padded = bytes.fromhex(address[2:].zfill(64))
    amount_padded = amount.to_bytes(32, "big")
    data = selector + addr_padded + amount_padded

    nonce = w3.eth.get_transaction_count(address)
    gas_price = w3.eth.gas_price

    tx = {
        "to": USDT_CONTRACT,
        "data": "0x" + data.hex(),
        "value": 0,
        "gas": 100000,
        "gasPrice": gas_price,
        "nonce": nonce,
        "chainId": CHAIN_ID,
    }

    signed = Account.sign_transaction(tx, pk)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    log(address, f"Faucet tx: {tx_hash.hex()}")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt.status == 1:
        log(address, "Faucet SUCCESS - dapat 100 USDT", "OK")
    else:
        log(address, "Faucet FAILED", "ERR")
    return receipt.status == 1

# ─── BIND REFERRAL ────────────────────────────────────────────────────────────

def do_bind_reff(wallet, reff_code=REFERRAL_CODE):
    address = wallet["address"]
    pk = wallet["pk"]

    # Check dulu apakah sudah bind
    resp = requests.get(
        f"{DATA_BASE_URL}/user/referral-profile",
        params={"user_address": address},
        timeout=30
    )
    data = resp.json().get("data", {})
    if data.get("has_bound_referrer"):
        log(address, f"Sudah bind reff: {data.get('bound_referral_code', '')}", "SKIP")
        return True

    # bindReferrer(bytes32 _code)
    # encode string to bytes32
    code_bytes = reff_code.encode("utf-8")
    code_padded = code_bytes + b"\x00" * (32 - len(code_bytes))

    selector = bytes.fromhex("65a46af4")
    data_hex = selector + code_padded

    nonce = w3.eth.get_transaction_count(address)
    gas_price = w3.eth.gas_price

    tx = {
        "to": REFF_CONTRACT,
        "data": "0x" + data_hex.hex(),
        "value": 0,
        "gas": 150000,
        "gasPrice": gas_price,
        "nonce": nonce,
        "chainId": CHAIN_ID,
    }

    signed = Account.sign_transaction(tx, pk)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    log(address, f"Bind reff tx: {tx_hash.hex()}")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt.status == 1:
        log(address, f"Bind reff SUCCESS - code: {reff_code}", "OK")
    else:
        log(address, "Bind reff FAILED", "ERR")
    return receipt.status == 1

# ─── APPROVE USDT ─────────────────────────────────────────────────────────────

def approve_usdt(wallet, spender, amount_wei):
    address = wallet["address"]
    pk = wallet["pk"]

    # Check allowance dulu
    # allowance(owner, spender) - 0xdd62ed3e
    sel = bytes.fromhex("dd62ed3e")
    owner_pad = bytes.fromhex(address[2:].zfill(64))
    spender_pad = bytes.fromhex(spender[2:].zfill(64))
    call_data = "0x" + (sel + owner_pad + spender_pad).hex()
    result = w3.eth.call({"to": USDT_CONTRACT, "data": call_data})
    current_allowance = int(result.hex(), 16)

    if current_allowance >= amount_wei:
        return True  # sudah approve

    # approve(spender, amount) - 0x095ea7b3
    sel_approve = bytes.fromhex("095ea7b3")
    max_amount = (2**256 - 1).to_bytes(32, "big")
    data = sel_approve + bytes.fromhex(spender[2:].zfill(64)) + max_amount

    nonce = w3.eth.get_transaction_count(address)
    gas_price = w3.eth.gas_price

    tx = {
        "to": USDT_CONTRACT,
        "data": "0x" + data.hex(),
        "value": 0,
        "gas": 100000,
        "gasPrice": gas_price,
        "nonce": nonce,
        "chainId": CHAIN_ID,
    }

    signed = Account.sign_transaction(tx, pk)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    log(address, f"Approve USDT tx: {tx_hash.hex()} | status: {'OK' if receipt.status == 1 else 'FAIL'}")
    return receipt.status == 1

# ─── GET LATEST PRICE ─────────────────────────────────────────────────────────

def get_latest_prices():
    try:
        resp = requests.get(ORACLE_URL, timeout=15)
        data = resp.json()
        return data
    except Exception as e:
        print(f"[WARN] Gagal fetch price: {e}")
        return {}

def get_btc_price():
    prices = get_latest_prices()
    # Cari BTC/USD dari response
    if isinstance(prices, list):
        for p in prices:
            if p.get("token_symbol") == "BTC" or "BTC" in str(p.get("symbol", "")):
                return int(p.get("min_price", 0)), int(p.get("max_price", 0))
    elif isinstance(prices, dict):
        for k, v in prices.items():
            if "BTC" in k.upper():
                if isinstance(v, dict):
                    return int(v.get("min", 0)), int(v.get("max", 0))
    # fallback dari activities data yang kita punya (BTC ~60k)
    btc_price = 60000 * 10**12  # dalam wei format hertz
    return btc_price, int(btc_price * 1.001)

# ─── ENCODE MULTICALL HELPERS ─────────────────────────────────────────────────

def encode_uint256(val):
    return val.to_bytes(32, "big")

def encode_address(addr):
    return bytes.fromhex(addr[2:].zfill(64))

def encode_bytes32(data_bytes):
    return data_bytes[:32].ljust(32, b"\x00")

def encode_bytes_array(items):
    """Encode bytes[] ABI"""
    n = len(items)
    # offset array
    result = encode_uint256(0x20)  # offset to array
    result += encode_uint256(n)    # array length

    # offsets for each element (relative to start of array data)
    data_offset = n * 32
    offsets = []
    for item in items:
        offsets.append(data_offset)
        # each item: 32 bytes length + padded data
        item_size = 32 + ((len(item) + 31) // 32) * 32
        data_offset += item_size

    for off in offsets:
        result += encode_uint256(off)

    for item in items:
        result += encode_uint256(len(item))
        padded = item + b"\x00" * ((32 - len(item) % 32) % 32)
        result += padded

    return result

# ─── LONG / SHORT ─────────────────────────────────────────────────────────────

def build_long_short_calldata(address, is_long, collateral_amount_wei, market_addr, price_min, price_max, reff_code=REFERRAL_CODE):
    """
    Build multicall calldata untuk open long/short
    Dari analisis tx 0x6248ae... dan 0xc895...

    Sub-calls:
    1. wrapNativeToken (7d39aaf1) - wrap BNB untuk execution fee
    2. sendTokens (e6d66ac8) - kirim USDT ke pool
    3. createOrder (699107b1) - create market order
    """

    # Encode referral code ke bytes32
    code_bytes = reff_code.encode("utf-8")
    reff_bytes32 = code_bytes + b"\x00" * (32 - len(code_bytes))

    # BNB execution fee (~0.005943 BNB dari tx analisis)
    exec_fee = 6000000000000000  # 0.006 BNB

    # 1. wrapNativeToken(address receiver)
    # method: 7d39aaf1, param: pool_address, exec_fee
    wrap_sel = bytes.fromhex("7d39aaf1")
    # params: pool address + execution fee amount
    pool_addr = POOL_CRYPTO  # BTC/USD menggunakan crypto pool
    wrap_call = wrap_sel + encode_address(pool_addr) + encode_uint256(exec_fee)

    # 2. sendTokens(address token, address receiver, uint256 amount)
    # method: e6d66ac8
    send_sel = bytes.fromhex("e6d66ac8")
    send_call = send_sel + encode_address(USDT_CONTRACT) + encode_address(pool_addr) + encode_uint256(collateral_amount_wei)

    # 3. createOrder - method 699107b1
    # Struktur dari tx data analisis
    create_sel = bytes.fromhex("699107b1")

    # Build order params (dari analisis calldata)
    # Offset ke struct
    order_offset = encode_uint256(0x20)

    # Struct fields (dari analisis):
    # referralCode, addresses, numbers, orderType, decreasePositionSwapType, isLong, shouldUnwrapNativeToken, autoCancel
    direction_val = encode_uint256(1 if is_long else 0)  # isLong
    order_type = encode_uint256(2)  # Market order = 2
    decrease_swap = encode_uint256(0)
    should_unwrap = encode_uint256(0)
    auto_cancel = encode_uint256(0)

    # Addresses struct offset
    addr_struct_offset = encode_uint256(0x220)  # dari analisis

    # Price params
    # size_usd = collateral * leverage (pakai 1.1x sesuai UI)
    # Dari analisis: size ~10970368233137459948048002885880 untuk collateral ~10 USDT
    # Ratio: size / collateral ≈ 1.097x leverage
    # Gunakan 1.1x leverage (collateral * 1.1 * price_precision)
    leverage_factor = 11  # 1.1x
    size_in_usd = collateral_amount_wei * price_min * leverage_factor // (10 * 10**18)
    if size_in_usd == 0:
        size_in_usd = collateral_amount_wei * 110 // 100  # fallback 1.1x

    acceptable_price = int(price_min * 0.99) if is_long else int(price_max * 1.01)

    # Build addresses struct (dari analisis tx)
    # [receiver, callbackContract, uiFeeReceiver, market, initialCollateralToken, ...]
    addr_data = (
        encode_address(address) +           # receiver
        encode_address("0x" + "00" * 20) +  # callbackContract
        encode_address("0x" + "00" * 20) +  # uiFeeReceiver
        encode_address(market_addr) +        # market
        encode_address(USDT_CONTRACT) +      # initialCollateralToken
        encode_uint256(0x100) +              # offset to swapPath
        encode_uint256(0x120) +              # offset to longTokenSwapPath
        encode_uint256(0) +                  # swapPath (empty)
        encode_uint256(0)                    # longTokenSwapPath (empty)
    )

    # Numbers struct
    num_data = (
        encode_uint256(size_in_usd) +         # sizeDeltaUsd
        encode_uint256(collateral_amount_wei) + # initialCollateralDeltaAmount
        encode_uint256(0) +                    # triggerPrice
        encode_uint256(acceptable_price) +     # acceptablePrice
        encode_uint256(exec_fee) +             # executionFee
        encode_uint256(0) +                    # callbackGasLimit
        encode_uint256(0) +                    # minOutputAmount
        encode_uint256(0)                      # validFromTime
    )

    # Build full struct
    struct_data = (
        reff_bytes32 +                 # referralCode (bytes32)
        addr_struct_offset +           # addresses offset
        encode_uint256(0x20 + len(addr_struct_offset) + 0x100) +  # numbers offset  
        order_type +
        decrease_swap +
        direction_val +
        should_unwrap +
        auto_cancel
    )

    # Simplify: pakai format yang sudah kita ketahui dari tx analisis
    # Format dari tx 0x6248ae (long BTC, 10 USDT collateral):
    inner = (
        encode_uint256(0x20) +           # offset to struct
        encode_uint256(0x220) +          # struct size hint
        reff_bytes32 +                   # referral code
        # nested addresses offset  
        encode_uint256(0) +              # placeholder
        encode_uint256(0) +
        encode_uint256(0) +
        encode_uint256(0) +
        encode_uint256(exec_fee) +       # execution fee
        encode_uint256(0) +
        encode_uint256(0) +
        encode_uint256(0) +
        encode_uint256(direction_val[31]) +  # isLong as uint
        encode_uint256(0) +
        encode_uint256(0) +
        encode_uint256(0) +
        encode_uint256(0x320) +          # addresses offset
        encode_address(address) +        # receiver
        encode_address("0x" + "00"*20) + # callback
        encode_address("0x" + "00"*20) + # ui fee receiver
        encode_address(market_addr) +    # market
        encode_address(USDT_CONTRACT) +  # collateral token
        encode_address(USDT_CONTRACT) +  # same
        encode_uint256(0x100) +
        encode_uint256(0x120) +
        encode_uint256(0) +
        encode_uint256(0) +
        encode_uint256(0)
    )

    create_call = create_sel + inner

    # Encode sebagai bytes[]
    sub_calls = [wrap_call, send_call, create_call]
    multicall_data = encode_bytes_array(sub_calls)

    # multicall(bytes[] data) - 0xac9650d8
    multicall_sel = bytes.fromhex("ac9650d8")
    return multicall_sel + multicall_data, exec_fee


def do_long(wallet, amount_usdt=None):
    address = wallet["address"]
    pk = wallet["pk"]

    if amount_usdt is None:
        amount_usdt = random.uniform(5, 15)
        amount_usdt = round(amount_usdt, 2)

    log(address, f"Open LONG BTC/USD | amount: {amount_usdt} USDT")

    price_min, price_max = get_btc_price()
    if price_min == 0:
        log(address, "Gagal dapat harga BTC", "ERR")
        return False

    amount_wei = usdt_to_wei(amount_usdt)
    market_addr = MARKETS["BTC/USD"]

    # Approve dulu
    approve_usdt(wallet, ROUTER_CONTRACT, amount_wei * 2)

    calldata, exec_fee = build_long_short_calldata(
        address, True, amount_wei,
        Web3.to_checksum_address(market_addr),
        price_min, price_max
    )

    nonce = w3.eth.get_transaction_count(address)
    gas_price = w3.eth.gas_price

    tx = {
        "to": ROUTER_CONTRACT,
        "data": "0x" + calldata.hex(),
        "value": exec_fee,
        "gas": 2000000,
        "gasPrice": gas_price,
        "nonce": nonce,
        "chainId": CHAIN_ID,
    }

    try:
        signed = Account.sign_transaction(tx, pk)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        log(address, f"Long tx: {tx_hash.hex()}")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
        if receipt.status == 1:
            log(address, f"Long SUCCESS | {amount_usdt} USDT", "OK")
        else:
            log(address, "Long FAILED", "ERR")
        return receipt.status == 1
    except Exception as e:
        log(address, f"Long error: {e}", "ERR")
        return False


def do_short(wallet, amount_usdt=None):
    address = wallet["address"]
    pk = wallet["pk"]

    if amount_usdt is None:
        amount_usdt = random.uniform(5, 15)
        amount_usdt = round(amount_usdt, 2)

    log(address, f"Open SHORT BTC/USD | amount: {amount_usdt} USDT")

    price_min, price_max = get_btc_price()
    if price_min == 0:
        log(address, "Gagal dapat harga BTC", "ERR")
        return False

    amount_wei = usdt_to_wei(amount_usdt)
    market_addr = MARKETS["BTC/USD"]

    approve_usdt(wallet, ROUTER_CONTRACT, amount_wei * 2)

    calldata, exec_fee = build_long_short_calldata(
        address, False, amount_wei,
        Web3.to_checksum_address(market_addr),
        price_min, price_max
    )

    nonce = w3.eth.get_transaction_count(address)
    gas_price = w3.eth.gas_price

    tx = {
        "to": ROUTER_CONTRACT,
        "data": "0x" + calldata.hex(),
        "value": exec_fee,
        "gas": 2000000,
        "gasPrice": gas_price,
        "nonce": nonce,
        "chainId": CHAIN_ID,
    }

    try:
        signed = Account.sign_transaction(tx, pk)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        log(address, f"Short tx: {tx_hash.hex()}")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
        if receipt.status == 1:
            log(address, f"Short SUCCESS | {amount_usdt} USDT", "OK")
        else:
            log(address, "Short FAILED", "ERR")
        return receipt.status == 1
    except Exception as e:
        log(address, f"Short error: {e}", "ERR")
        return False

# ─── POOL ─────────────────────────────────────────────────────────────────────

def build_pool_calldata(address, pool_addr, usdt_amount_wei, bnb_amount_wei, market_addr):
    """
    Build multicall untuk add liquidity ke pool
    Dari analisis tx pool forex (0xff364972)

    Sub-calls:
    1. wrapNativeToken - wrap BNB
    2. sendTokens - kirim USDT
    3. createDeposit (c82aa41b untuk pool) - create deposit order
    """

    exec_fee = bnb_amount_wei

    # 1. wrapNativeToken
    wrap_sel = bytes.fromhex("7d39aaf1")
    wrap_call = wrap_sel + encode_address(pool_addr) + encode_uint256(exec_fee)

    # 2. sendTokens(USDT, pool, amount)
    send_sel = bytes.fromhex("e6d66ac8")
    send_call = send_sel + encode_address(USDT_CONTRACT) + encode_address(pool_addr) + encode_uint256(usdt_amount_wei)

    # 3. createDeposit (c82aa41b dari analisis tx pool forex)
    create_sel = bytes.fromhex("c82aa41b")

    # Params dari analisis tx pool 0xff364972
    inner = (
        encode_uint256(0x20) +           # offset
        encode_uint256(0xc0) +           # nested offset
        encode_uint256(0) +              # placeholder price
        encode_uint256(exec_fee) +       # executionFee
        encode_uint256(0) +
        encode_uint256(0) +
        encode_uint256(0) +
        encode_uint256(0x200) +          # addresses offset
        encode_address(address) +        # receiver
        encode_address("0x" + "00"*20) + # callbackContract
        encode_address("0x" + "00"*20) + # uiFeeReceiver
        encode_address(market_addr) +    # market
        encode_address(USDT_CONTRACT) +  # initialLongToken
        encode_address(USDT_CONTRACT) +  # initialShortToken
        encode_uint256(0x100) +
        encode_uint256(0x120) +
        encode_uint256(0) +
        encode_uint256(0) +
        encode_uint256(0)
    )

    create_call = create_sel + inner

    sub_calls = [wrap_call, send_call, create_call]
    multicall_data = encode_bytes_array(sub_calls)

    multicall_sel = bytes.fromhex("ac9650d8")
    return multicall_sel + multicall_data, exec_fee


def do_pool(wallet, amount_usdt=None, pool_type="forex"):
    address = wallet["address"]
    pk = wallet["pk"]

    if amount_usdt is None:
        amount_usdt = random.uniform(10, 30)
        amount_usdt = round(amount_usdt, 2)

    pool_addr = POOL_FOREX if pool_type == "forex" else POOL_CRYPTO
    pool_name = "USD/TRY (Forex)" if pool_type == "forex" else "BTC/USD (Crypto)"
    # Market address untuk pool
    market_addr = "0xaE2Ba965Cf653631737835c5679f6949D8DB3164" if pool_type == "forex" else MARKETS["BTC/USD"]

    log(address, f"Add Liquidity Pool {pool_name} | {amount_usdt} USDT")

    amount_wei = usdt_to_wei(amount_usdt)
    bnb_fee = bnb_to_wei(0.006)  # ~0.006 BNB exec fee

    approve_usdt(wallet, ROUTER_CONTRACT, amount_wei * 2)

    calldata, exec_fee = build_pool_calldata(
        address,
        Web3.to_checksum_address(pool_addr),
        amount_wei,
        bnb_fee,
        Web3.to_checksum_address(market_addr)
    )

    nonce = w3.eth.get_transaction_count(address)
    gas_price = w3.eth.gas_price

    tx = {
        "to": ROUTER_CONTRACT,
        "data": "0x" + calldata.hex(),
        "value": exec_fee,
        "gas": 2000000,
        "gasPrice": gas_price,
        "nonce": nonce,
        "chainId": CHAIN_ID,
    }

    try:
        signed = Account.sign_transaction(tx, pk)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        log(address, f"Pool tx: {tx_hash.hex()}")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
        if receipt.status == 1:
            log(address, f"Pool SUCCESS | {amount_usdt} USDT ke {pool_name}", "OK")
        else:
            log(address, "Pool FAILED", "ERR")
        return receipt.status == 1
    except Exception as e:
        log(address, f"Pool error: {e}", "ERR")
        return False

# ─── VAULT ────────────────────────────────────────────────────────────────────

def build_vault_calldata(address, vault_pool_addr, usdt_amount_wei, bnb_amount_wei, vault_market_addr):
    """
    Build multicall untuk deposit ke vault
    Dari analisis tx vault 0xeffafac4 - router berbeda: 0x9A8958B6...
    Function createDeposit: c31d4ea8
    """

    exec_fee = bnb_amount_wei

    # 1. wrapNativeToken
    wrap_sel = bytes.fromhex("7d39aaf1")
    wrap_call = wrap_sel + encode_address(vault_pool_addr) + encode_uint256(exec_fee)

    # 2. sendTokens
    send_sel = bytes.fromhex("e6d66ac8")
    send_call = send_sel + encode_address(USDT_CONTRACT) + encode_address(vault_pool_addr) + encode_uint256(usdt_amount_wei)

    # 3. createDeposit vault (c31d4ea8 dari analisis tx vault)
    create_sel = bytes.fromhex("c31d4ea8")

    # Dari analisis tx vault 0xeffafac4
    # market_addr di vault adalah vault_market_addr (0x79Bba0A9...)
    inner = (
        encode_uint256(0x20) +
        encode_uint256(0xe0) +
        encode_uint256(0) +
        encode_uint256(exec_fee) +
        encode_uint256(0) +
        encode_uint256(0) +
        encode_uint256(0) +
        encode_uint256(0) +
        encode_uint256(0x240) +
        encode_address(address) +         # receiver
        encode_address(vault_market_addr) + # callbackContract (vault market)
        encode_address("0x" + "00"*20) +  # uiFeeReceiver
        encode_address(vault_market_addr) + # market
        encode_address(USDT_CONTRACT) +
        encode_address(USDT_CONTRACT) +
        encode_uint256(0x100) +
        encode_uint256(0x120) +
        encode_uint256(0) +
        encode_uint256(0) +
        encode_uint256(0)
    )

    create_call = create_sel + inner

    sub_calls = [wrap_call, send_call, create_call]
    multicall_data = encode_bytes_array(sub_calls)

    multicall_sel = bytes.fromhex("ac9650d8")
    return multicall_sel + multicall_data, exec_fee


def do_vault(wallet, amount_usdt=None):
    address = wallet["address"]
    pk = wallet["pk"]

    if amount_usdt is None:
        amount_usdt = random.uniform(10, 30)
        amount_usdt = round(amount_usdt, 2)

    # Vault market address dari activities: 0x79Bba0A9Ad45362404173E33d330c5eA6E02EE08
    vault_market = "0x79Bba0A9Ad45362404173E33d330c5eA6E02EE08"

    log(address, f"Deposit Vault Tech Giants | {amount_usdt} USDT")

    amount_wei = usdt_to_wei(amount_usdt)
    bnb_fee = bnb_to_wei(0.008)  # sedikit lebih dari pool

    approve_usdt(wallet, VAULT_ROUTER, amount_wei * 2)

    calldata, exec_fee = build_vault_calldata(
        address,
        VAULT_POOL,
        amount_wei,
        bnb_fee,
        Web3.to_checksum_address(vault_market)
    )

    nonce = w3.eth.get_transaction_count(address)
    gas_price = w3.eth.gas_price

    tx = {
        "to": VAULT_ROUTER,
        "data": "0x" + calldata.hex(),
        "value": exec_fee,
        "gas": 2000000,
        "gasPrice": gas_price,
        "nonce": nonce,
        "chainId": CHAIN_ID,
    }

    try:
        signed = Account.sign_transaction(tx, pk)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        log(address, f"Vault tx: {tx_hash.hex()}")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
        if receipt.status == 1:
            log(address, f"Vault SUCCESS | {amount_usdt} USDT", "OK")
        else:
            log(address, "Vault FAILED", "ERR")
        return receipt.status == 1
    except Exception as e:
        log(address, f"Vault error: {e}", "ERR")
        return False

# ─── BALANCE ──────────────────────────────────────────────────────────────────

def do_balance(wallet):
    address = wallet["address"]
    addr_short = address[:6] + "..." + address[-4:]

    # 1. USDT balance onchain
    sel = bytes.fromhex("70a08231")
    call_data = "0x" + (sel + bytes.fromhex(address[2:].zfill(64))).hex()
    result = w3.eth.call({"to": USDT_CONTRACT, "data": call_data})
    usdt_bal = int(result.hex(), 16)

    # 2. BNB balance
    bnb_bal = w3.eth.get_balance(address)

    # 3. Vault info
    try:
        resp = requests.get(f"{DATA_BASE_URL}/vaults", params={"wallet_address": address}, timeout=15)
        vault_data = resp.json().get("data", {})
    except:
        vault_data = {}

    # 4. Activities (PnL dari trading)
    try:
        resp2 = requests.get(
            f"{DATA_BASE_URL}/user/activities",
            params={"account": address, "limit": 20},
            timeout=15
        )
        activities = resp2.json().get("data", {}).get("activities", [])
    except:
        activities = []

    print(f"\n+--- Balance: {addr_short} ---+")
    print(f"  BNB  : {bnb_bal / 10**18:.6f}")
    print(f"  USDT : {usdt_bal / 10**18:.4f}")

    if vault_data:
        print(f"\n  Vault/Pool Info:")
        if isinstance(vault_data, dict):
            for k, v in vault_data.items():
                if "usd" in k.lower() or "share" in k.lower() or "value" in k.lower():
                    print(f"    {k}: {v}")
        elif isinstance(vault_data, list):
            for item in vault_data:
                print(f"    {item.get('symbol', '?')}: {item.get('usd_value', 0)} USD")

    # Hitung PnL dari activities
    total_pnl = 0
    open_positions = []
    for act in activities:
        if act.get("action_type") == "trade":
            direction = act.get("direction", "?")
            market = act.get("market_symbol", "?")
            action = act.get("action", "?")
            size = float(act.get("size_in_usd", 0)) / 10**30
            print(f"  Trade: {action} {direction.upper()} {market} | size: ${size:.2f}")

    print("+----------------------------+\n")

# ─── MAIN FLOW ────────────────────────────────────────────────────────────────

def run_wallet(wallet, mode):
    address = wallet["address"]

    if mode == "balance":
        do_balance(wallet)
        return

    if mode in ("faucet", "all"):
        log(address, "=== FAUCET ===")
        do_faucet(wallet)
        time.sleep(3)

    if mode in ("bind_reff", "all"):
        log(address, "=== BIND REFERRAL ===")
        do_bind_reff(wallet)
        time.sleep(3)

    if mode in ("long", "all"):
        log(address, "=== LONG ===")
        amount = random.uniform(5, 15)
        do_long(wallet, round(amount, 2))
        time.sleep(5)

    if mode in ("short", "all"):
        log(address, "=== SHORT ===")
        amount = random.uniform(5, 15)
        do_short(wallet, round(amount, 2))
        time.sleep(5)

    if mode in ("pool", "all"):
        log(address, "=== POOL ===")
        # Random pilih forex atau crypto
        pool_type = random.choice(["forex", "crypto"])
        amount = random.uniform(10, 25)
        do_pool(wallet, round(amount, 2), pool_type)
        time.sleep(5)

    if mode in ("vault", "all"):
        log(address, "=== VAULT ===")
        amount = random.uniform(10, 30)
        do_vault(wallet, round(amount, 2))
        time.sleep(3)


def main():
    banner()

    wallets = load_wallets("wallets.txt")
    if not wallets:
        print("[ERROR] Tidak ada wallet ditemukan")
        sys.exit(1)

    selected = select_accounts(wallets)
    mode = select_mode()

    print(f"\nMode: {mode.upper()} | Akun: {len(selected)}")
    print("-" * 50)

    for i, wallet in enumerate(selected):
        print(f"\n[{i+1}/{len(selected)}] Processing {wallet['address']}")
        try:
            run_wallet(wallet, mode)
        except Exception as e:
            log(wallet["address"], f"Error: {e}", "ERR")
            import traceback
            traceback.print_exc()

        if i < len(selected) - 1:
            delay = random.randint(5, 15)
            print(f"Delay {delay}s sebelum akun berikutnya...")
            time.sleep(delay)

    print("\n+--- SELESAI ---+")


if __name__ == "__main__":
    main()

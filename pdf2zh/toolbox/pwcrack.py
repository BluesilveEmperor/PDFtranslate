import hashlib
import itertools
import multiprocessing as mp
import os
import re
import struct

_PAD = bytes.fromhex("28bf4e5e4e758a4164004e56fffa01082e2e00b6d0683e802f0ca9fe6453697a")

DEFAULT_CHARSET = "abcdefghijklmnopqrstuvwxyz0123456789"

COMMON_PASSWORDS = [
    "123456", "password", "123456789", "12345678", "1234567890", "111111",
    "123123", "abc123", "1234", "12345", "000000", "666666", "888888",
    "1234567", "admin", "admin123", "test", "test123", "a123456", "123321",
    "121212", "112233", "qwe123", "1qaz2wsx", "aa123456", "woaini",
    "woaini520", "147258369", "987654321", "520520", "111222", "123654",
    "159357", "753951", "woaini1314", "zxcvbnm", "asdfghjkl", "qwerty",
    "qwertyuiop", "1q2w3e4r", "p@ssw0rd", "passw0rd", "iloveyou", "sunshine",
    "princess", "dragon", "monkey", "letmein", "welcome", "master", "shadow",
    "football", "baseball", "superman", "batman", "trustno1", "654321",
    "555555", "101010", "131313", "202020", "212121", "321321", "456789",
    "565656", "789456", "876543", "secret", "abcdef", "abcdefg", "aaaaaa",
    "qq123456", "woshiwo", "5201314", "1a2b3c", "qazwsx", "147258", "369258",
    "159753", "741852", "963852", "asd123", "zxc123", "123000", "007007",
    "100200", "10086", "123456a", "123123123", "asdf1234", "root", "pass",
    "pass123", "user", "guest", "mail", "home", "love", "angel", "flower",
    "happy", "smile", "freedom", "whatever", "zaq12wsx", "123qwe", "qweasd",
    "142536", "132435", "102030", "11223344", "12341234", "567890", "0987654321",
]


class CrackError(Exception):
    pass


#: 暴力枚举的硬上限：最大密码长度。超过即拒绝执行，避免指数级候选爆炸。
MAX_BRUTE_LEN = 8

#: 暴力枚举候选总数上限。超过即拒绝执行，防止局域网可达的 GUI 被拖垮（DoS）。
MAX_BRUTE_CANDIDATES = 5_000_000


def clamp_jobs(jobs=None):
    """把并行进程数限制在 ``[1, os.cpu_count()]`` 之间。

    ``None``/空值/非法值回退到 CPU 核数；结果至少为 1，至多不超过 CPU 核数，
    避免调用方传入超大值创建海量进程。
    """
    cpu = os.cpu_count() or 4
    if jobs is None or jobs == "":
        return cpu
    try:
        value = int(jobs)
    except (TypeError, ValueError):
        return cpu
    return max(1, min(value, cpu))


def brute_candidate_count(charset, min_len, max_len):
    """计算暴力枚举的候选总数 ``Σ len(charset)**l``。"""
    return sum(len(charset) ** length for length in range(min_len, max_len + 1))


def _pad32(pw):
    return (pw[:32] + _PAD)[:32]


def _rc4(key, data):
    S = list(range(256))
    j = 0
    klen = len(key)
    for i in range(256):
        j = (j + S[i] + key[i % klen]) & 0xFF
        S[i], S[j] = S[j], S[i]
    out = bytearray()
    i = j = 0
    for b in data:
        i = (i + 1) & 0xFF
        j = (j + S[i]) & 0xFF
        S[i], S[j] = S[j], S[i]
        out.append(b ^ S[(S[i] + S[j]) & 0xFF])
    return bytes(out)


def _aes_cbc_encrypt(key, iv, data):
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return enc.update(data) + enc.finalize()


def _hash_r56(password, salt, udata, R):
    k = hashlib.sha256(password + salt + udata).digest()
    if R < 6:
        return k
    count = 0
    while True:
        count += 1
        k1 = (password + k + udata) * 64
        e = _aes_cbc_encrypt(k[:16], k[16:32], k1)
        fn = (hashlib.sha256, hashlib.sha384, hashlib.sha512)[sum(e[:16]) % 3]
        k = fn(e).digest()
        if count >= 64 and e[-1] <= count - 32:
            break
    return k[:32]


_ESCAPES = {ord("n"): b"\n", ord("r"): b"\r", ord("t"): b"\t", ord("b"): b"\b",
            ord("f"): b"\f", ord("("): b"(", ord(")"): b")", ord("\\"): b"\\"}


def _parse_pdf_string(data, pos):
    if data[pos:pos + 1] == b"<":
        end = data.index(b">", pos)
        hexpart = re.sub(rb"\s", b"", data[pos + 1:end])
        return bytes.fromhex(hexpart.decode("ascii")), end + 1
    out = bytearray()
    i = pos + 1
    depth = 1
    n = len(data)
    while i < n:
        b = data[i]
        if b == 0x5C:
            if i + 1 >= n:
                break
            nxt = data[i + 1]
            if nxt in _ESCAPES:
                out += _ESCAPES[nxt]
                i += 2
            elif 0x30 <= nxt <= 0x37:
                val = 0
                cnt = 0
                while cnt < 3 and i + 1 + cnt < n and 0x30 <= data[i + 1 + cnt] <= 0x37:
                    val = val * 8 + (data[i + 1 + cnt] - 0x30)
                    cnt += 1
                out.append(val & 0xFF)
                i += 1 + cnt
            elif nxt in (0x0D, 0x0A):
                i += 2
                if nxt == 0x0D and i < n and data[i] == 0x0A:
                    i += 1
            else:
                out.append(nxt)
                i += 2
        elif b == 0x28:
            depth += 1
            out.append(b)
            i += 1
        elif b == 0x29:
            depth -= 1
            if depth == 0:
                return bytes(out), i + 1
            out.append(b)
            i += 1
        else:
            out.append(b)
            i += 1
    raise CrackError("PDF 字符串解析失败：括号未闭合")


def _find_key_string(d, key):
    m = re.search(rb"/" + key + rb"(?![A-Za-z])\s*(<|\()", d)
    if not m:
        return None
    val, _ = _parse_pdf_string(d, m.start(1))
    return val


def _extract_object(data, num, gen):
    pat = re.compile(rb"(?<![0-9])" + str(num).encode() + rb"\s+" + str(gen).encode() + rb"\s+obj")
    matches = list(pat.finditer(data))
    if not matches:
        raise CrackError(f"未找到加密字典对象 {num} {gen} obj")
    start = matches[-1].end()
    end = data.find(b"endobj", start)
    if end < 0:
        raise CrackError("加密字典对象不完整")
    return data[start:end]


def _extract_direct_dict(data, start):
    depth = 0
    i = start
    n = len(data)
    while i < n - 1:
        if data[i:i + 2] == b"<<":
            depth += 1
            i += 2
        elif data[i:i + 2] == b">>":
            depth -= 1
            i += 2
            if depth == 0:
                return data[start:i]
        else:
            i += 1
    raise CrackError("加密字典解析失败")


def parse_encryption_info(path):
    with open(path, "rb") as f:
        data = f.read()
    refs = list(re.finditer(rb"/Encrypt\s+(\d+)\s+(\d+)\s+R\b", data))
    if refs:
        num = int(refs[-1].group(1))
        gen = int(refs[-1].group(2))
        d = _extract_object(data, num, gen)
    else:
        m = re.search(rb"/Encrypt\s*<<", data)
        if not m:
            return None
        d = _extract_direct_dict(data, m.end() - 2)
    if re.search(rb"/Filter\s*/(\w+)", d):
        filt = re.search(rb"/Filter\s*/(\w+)", d).group(1)
        if filt != b"Standard":
            raise CrackError(f"非标准加密处理器: {filt.decode(errors='replace')}")
    rm = re.search(rb"/R\s+(\d+)", d)
    vm = re.search(rb"/V\s+(\d+)", d)
    if not rm or not vm:
        raise CrackError("加密字典缺少 /R 或 /V")
    R = int(rm.group(1))
    V = int(vm.group(1))
    info = {"R": R, "V": V}
    lm = re.search(rb"/Length\s+(\d+)", d)
    if lm:
        info["Length"] = int(lm.group(1))
    elif V == 1 or R == 2:
        info["Length"] = 40
    elif R >= 5:
        info["Length"] = 256
    else:
        info["Length"] = 128
    pm = re.search(rb"/P\s+(-?\d+)", d)
    if not pm:
        raise CrackError("加密字典缺少 /P")
    info["P"] = int(pm.group(1))
    info["O"] = _find_key_string(d, b"O")
    info["U"] = _find_key_string(d, b"U")
    if info["O"] is None or info["U"] is None:
        raise CrackError("加密字典缺少 /O 或 /U")
    em = re.search(rb"/EncryptMetadata\s+(true|false)", d)
    info["MetadataEncrypted"] = (em is None) or (em.group(1) == b"true")
    idm = list(re.finditer(rb"/ID\s*\[\s*<([0-9A-Fa-f\s]+)>", data))
    if idm:
        info["ID0"] = bytes.fromhex(re.sub(rb"\s", b"", idm[-1].group(1)).decode("ascii"))
    else:
        idl = re.search(rb"/ID\s*\[\s*\(", data)
        if idl:
            info["ID0"], _ = _parse_pdf_string(data, idl.end() - 1)
        else:
            info["ID0"] = b""
    if R >= 5 and (len(info["U"]) < 48 or len(info["O"]) < 48):
        raise CrackError("R5/R6 加密字典 /U /O 长度异常")
    if R < 5 and (len(info["U"]) < 32 or len(info["O"]) < 32):
        raise CrackError("加密字典 /U /O 长度异常")
    return info


def make_verifier(info):
    R = info["R"]
    if R >= 5:
        U = info["U"]
        O = info["O"]

        def verify(pw):
            b = pw.encode("utf-8", "surrogateescape")[:127]
            if _hash_r56(b, U[32:40], b"", R) == U[:32]:
                return True
            if _hash_r56(b, O[32:40], U, R) == O[:32]:
                return True
            return False

        return verify
    O = info["O"]
    U = info["U"]
    P = info["P"]
    id0 = info["ID0"]
    keylen = 5 if R == 2 else max(5, min(info["Length"] // 8, 16))
    md_enc = info["MetadataEncrypted"]
    pbytes = struct.pack("<I", P & 0xFFFFFFFF)
    xtra = b"\xff\xff\xff\xff" if (R >= 4 and not md_enc) else b""

    def verify(pw):
        pwb = pw.encode("utf-8", "surrogateescape")
        h = hashlib.md5(_pad32(pwb) + O + pbytes + id0 + xtra)
        dg = h.digest()
        if R >= 3:
            for _ in range(50):
                dg = hashlib.md5(dg[:keylen]).digest()
        key = dg[:keylen]
        if R == 2:
            return _rc4(key, _PAD) == U
        x = _rc4(key, hashlib.md5(_PAD + id0).digest())
        for i in range(1, 20):
            x = _rc4(bytes(kb ^ i for kb in key), x)
        return x == U[:16]

    return verify


def brute_candidates(charset, min_len, max_len):
    for l in range(min_len, max_len + 1):
        for tup in itertools.product(charset, repeat=l):
            yield "".join(tup)


def wordlist_candidates(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            w = line.rstrip("\r\n")
            if w and not w.startswith("#"):
                yield w


def _brute_worker(args):
    info, charset, min_len, max_len, wid, njobs = args
    verify = make_verifier(info)
    it = brute_candidates(charset, min_len, max_len)
    for pw in itertools.islice(it, wid, None, njobs):
        if verify(pw):
            return pw
    return None


def crack(path, wordlist=None, charset=None, min_len=1, max_len=4, jobs=None, log=None):
    log = log or (lambda *a: None)
    info = parse_encryption_info(path)
    if info is None:
        raise CrackError("未找到加密字典（文件可能未加密或使用非标准处理器）")
    verify = make_verifier(info)
    log(f"加密信息: R={info['R']} V={info['V']} Length={info['Length']}")
    log("阶段 1/3: 尝试内置常见密码...")
    for pw in COMMON_PASSWORDS:
        if verify(pw):
            return pw
    if wordlist:
        log(f"阶段 2/3: 字典攻击 ({wordlist})...")
        for pw in wordlist_candidates(wordlist):
            if verify(pw):
                return pw
    else:
        log("阶段 2/3: 未提供字典，跳过")
    if max_len is None or max_len == "":
        max_len = 4
    if min_len is None or min_len == "":
        min_len = 1
    max_len = int(max_len)
    min_len = int(min_len)
    if max_len < min_len:
        return None
    if max_len > MAX_BRUTE_LEN:
        raise CrackError(
            f"最大长度 {max_len} 超过硬上限 {MAX_BRUTE_LEN}，请缩小枚举范围"
        )
    cs = charset or DEFAULT_CHARSET
    total = brute_candidate_count(cs, min_len, max_len)
    if total <= 0:
        return None
    if total > MAX_BRUTE_CANDIDATES:
        raise CrackError(
            f"暴力枚举候选数 {total:,} 超过上限 {MAX_BRUTE_CANDIDATES:,}，"
            "请缩小字符集或长度范围"
        )
    jobs = clamp_jobs(jobs)
    log(f"阶段 3/3: 暴力枚举 charset={len(cs)}字符 len {min_len}-{max_len} 候选≈{total:,} 并行={jobs}...")
    if jobs <= 1:
        for pw in brute_candidates(cs, min_len, max_len):
            if verify(pw):
                return pw
        return None
    ctx = mp.get_context("spawn")
    tasks = [(info, cs, min_len, max_len, i, jobs) for i in range(jobs)]
    with ctx.Pool(jobs) as pool:
        for res in pool.imap_unordered(_brute_worker, tasks):
            if res:
                pool.terminate()
                return res
    return None

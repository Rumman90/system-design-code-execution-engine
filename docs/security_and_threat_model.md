# Security & Threat Model: The 6 Attack Vectors

A clear, non-academic breakdown of the real-world attacks hackers and malicious users attempt against code execution engines and how our architecture neutralizes each one.

---

## Threat Matrix Overview

| Attack Vector | Hacker's Objective | Defensive Countermeasure |
| :--- | :--- | :--- |
| **1. Denial of Service (DoS)** | Exhaust CPU, RAM, or Process IDs to crash the platform. | cgroups v2 (`memory.max`, `cpu.max`, `pids.max`) + Watchdog timer. |
| **2. Cloud Pivot & SSRF** | Steal AWS/GCP cloud credentials from `169.254.169.254`. | Network namespace with no route (`--net=none`) + eBPF firewall. |
| **3. Filesystem Tampering** | Read `/etc/shadow`, steal other users' code, or overwrite OS files. | Read-only root filesystem (`tmpfs` ephemeral overlay). |
| **4. Crypto-Mining & Botnets** | Run background miners (Monero) or join DDoS botnets. | No external network access + strict 5-second process timeout. |
| **5. Kernel Privilege Escalation** | Exploit kernel bugs (e.g. Dirty COW) to gain root on the host. | User namespaces (root in jail = nobody on host) + Seccomp syscall filtering. |
| **6. Disk Space Exhaustion** | Write 100GB dummy files to fill the host server's hard drive. | Read-only filesystem with a tiny 16MB in-memory `tmpfs` writable directory. |

---

## Deep Dive into the Top 3 Critical Exploits

### 1. Server-Side Request Forgery (SSRF) & Metadata Theft
* **The Exploit:** In cloud providers (AWS, GCP, Azure), virtual machines can query an internal, unauthenticated link (`http://169.254.169.254/latest/meta-data/`) to retrieve temporary IAM security credentials.
* **Malicious Script:**
  ```python
  import urllib.request
  token = urllib.request.urlopen("http://169.254.169.254/latest/meta-data/iam/security-credentials/").read()
  print("Stolen Cloud Credentials:", token)
  ```
* **The Fix:**
  * The sandbox container has **no default network interface** (`eth0` does not exist).
  * Only loopback (`127.0.0.1`) is configured.
  * The network request fails immediately with `Network is unreachable` in 0.001ms.

---

### 2. The Linux Fork Bomb
* **The Exploit:** Rapidly spawning infinite processes recursively until the host runs out of process IDs (PIDs), causing the whole server to freeze and stop responding to SSH.
* **Malicious Script:**
  ```bash
  :(){ :|:& };:
  # Or in Python:
  import os
  while True:
      os.fork()
  ```
* **The Fix:**
  * Inside Linux cgroups v2, we enforce:
    ```bash
    echo 20 > /sys/fs/cgroup/sandbox_user/pids.max
    ```
  * Once 20 processes exist, the 21st `os.fork()` call fails instantly with `BlockingIOError / EAGAIN`. The script cannot freeze the host.

---

### 3. Disk Filling Bombs
* **The Exploit:** Writing an endless file to disk until the server runs out of storage:
  ```python
  with open("malicious.bin", "wb") as f:
      while True:
          f.write(b"0" * 1024 * 1024)
  ```
* **The Fix:**
  * The root filesystem is mounted as **strictly Read-Only (`ro`)**.
  * If the user code needs to write temporary files (e.g. `test.txt`), we provide a virtual directory `/tmp` mounted on **`tmpfs`** (RAM disk) with a maximum cap of **16 MB**.
  * Any write exceeding 16 MB immediately throws `OSError: [Errno 28] No space left on device`.
  * Physical hard drives on the host machine are never touched!

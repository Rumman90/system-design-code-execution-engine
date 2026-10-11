# Isolation & Sandboxing: How to Tame Untrusted Code

A beginner-friendly guide to Linux isolation technologies: how we trap untrusted code so it cannot harm the server or read private files.

---

## 1. The Core Problem: Shared Kernel Vulnerability

In everyday computing, multiple programs share the same operating system kernel:

```
  [ Your Python Script ]     [ Database ]     [ SSH Server ]
           │                       │                │
           └───────────────────────┼────────────────┘
                                   ▼
                        [ Shared Linux Kernel ]
```

If a user writes code that crashes the kernel, deletes files in `/etc/`, or runs out of RAM, **every other program on the machine dies too**.

To make a sandbox, we must construct an invisible barrier around the user's code.

---

## 2. Linux Namespaces: The Invisible Box

Namespaces tell a process: *"You can only see the things in your designated room."*

| Namespace | What It Hides | Why It Matters for a Code Sandbox |
| :--- | :--- | :--- |
| **PID (Process ID)** | Hides all other running programs. | The user's code thinks it is PID `1`. It cannot run `kill -9` on the host web server. |
| **MNT (Mount/Filesystem)** | Hides the real hard drive directories. | The code only sees a minimal virtual folder with standard language libraries. `/etc/shadow` and host code do not exist. |
| **NET (Network)** | Hides network cards and sockets. | Defaults to loopback only (`127.0.0.1`). The code cannot ping external servers, download bitcoin miners, or attack the cloud network. |
| **USER** | Maps root inside the sandbox to an unprivileged nobody on host. | Even if the user code exploits `sudo`, it has zero root privileges on the actual server. |
| **IPC (Inter-Process)** | Isolates shared memory. | Prevents reading cached memory buffers belonging to other users. |

---

## 3. Control Groups (cgroups v2): The Resource Enforcer

While Namespaces hide things, **cgroups** meter and restrict hardware consumption. 

In Linux cgroups v2, limits are configured by writing simple text files:

```bash
# 1. Limit Memory to 256MB
echo "268435456" > /sys/fs/cgroup/sandbox_user_42/memory.max

# 2. Limit CPU to 1 core max (100,000 microseconds per 100,000 microsecond period)
echo "100000 100000" > /sys/fs/cgroup/sandbox_user_42/cpu.max

# 3. Limit Process count to 20 (Prevents Fork Bombs)
echo "20" > /sys/fs/cgroup/sandbox_user_42/pids.max
```

### What happens when limits are breached?
* **Memory Exceeded:** The Linux kernel Out-Of-Memory (OOM) killer fires immediately and terminates the process with exit code `137` (SIGKILL).
* **CPU Exceeded:** The OS scheduler throttles CPU execution time without killing the process.
* **PIDs Exceeded:** Any attempt to call `fork()` or `pthread_create()` fails with `EAGAIN` (Resource temporarily unavailable).

---

## 4. Seccomp: The Syscall Bouncer

Programs interact with the operating system using **System Calls (syscalls)**. There are over 300 syscalls in Linux (e.g., `open`, `read`, `write`, `socket`, `reboot`).

Most user code only needs a tiny handful (~30 syscalls) to calculate algorithms:
* `read`, `write` (for stdin/stdout)
* `exit_group` (to terminate cleanly)
* `mmap`, `brk` (to allocate memory)

With **Secure Computing Mode (Seccomp-BPF)**, we configure a strict whitelist filter:

```c
// Pseudo-code Seccomp Policy:
if (syscall == SYS_reboot)     -> KILL_PROCESS;
if (syscall == SYS_ptrace)     -> KILL_PROCESS; // Anti-debugging
if (syscall == SYS_socket)     -> KILL_PROCESS; // No network
if (syscall == SYS_mount)      -> KILL_PROCESS; // No mounting drives
else                           -> ALLOW;
```

If user code tries to invoke a forbidden syscall, the kernel immediately kills the thread before the syscall is ever executed.

---

## 5. Technology Comparison: Docker vs gVisor vs Firecracker

Which sandboxing technology should you pick for an RCE platform?

| Technology | Isolation Type | Boot Overhead | Security Level | Best Used For |
| :--- | :--- | :--- | :--- | :--- |
| **Vanilla Docker** | Shared Kernel (cgroups + namespaces) | ~1,000ms | ⚠️ Medium (Kernel exploit = Host takeover) | Internal CI/CD pipelines, trusted developers |
| **gVisor (Google)** | User-space Kernel (Intercepts syscalls in Go) | ~150ms | 🛡️ High (Simulates kernel, no direct host syscalls) | Google Cloud Run, multi-tenant web apps |
| **Firecracker (AWS)** | MicroVM (KVM hardware virtualization) | **~5ms** | 🔒 Maximum (Independent isolated Linux kernel) | AWS Lambda, Fly.io, Untrusted Public Code Run |
| **nsjail (Google)** | Lightweight Linux jail (Chroot + Seccomp + cgroups) | **< 2ms** | 🛡️ High (Ultra fast, lightweight wrapper) | Competitive programming, LeetCode style judges |

### The Winning Production Architecture:
* For **LeetCode / Single Script Judges:** Use **nsjail** or **Firecracker** because their startup overhead is practically zero (< 5ms) and they provide rock-solid isolation.

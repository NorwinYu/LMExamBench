"""A tiny OpenAI-compatible mock server for offline smoke tests.

It is NOT a real model. It returns canned answers so the full pipeline
(client -> runner -> grader -> scorer -> web) can be exercised without a GPU.
Run:  python3 tests/mock_model.py --port 18080
"""
from __future__ import annotations

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CODE_IMPLS = {
    "two_sum": "def two_sum(nums, target):\n"
               "    seen = {}\n"
               "    for i, n in enumerate(nums):\n"
               "        if target - n in seen:\n"
               "            return [seen[target - n], i]\n"
               "        seen[n] = i\n",
    "reverse_list": "def reverse_list(s):\n"
                    "    return list(reversed(s))\n",
    "fib": "def fib(n):\n"
           "    a, b = 0, 1\n"
           "    for _ in range(n):\n"
           "        a, b = b, a + b\n"
           "    return a\n",
    "is_palindrome": "def is_palindrome(s):\n"
                     "    return s == s[::-1]\n",
    "max_subarray": "def max_subarray(nums):\n"
                    "    best = cur = nums[0]\n"
                    "    for n in nums[1:]:\n"
                    "        cur = max(n, cur + n)\n"
                    "        best = max(best, cur)\n"
                    "    return best\n",
    "binary_search": "def binary_search(nums, target):\n"
                     "    lo, hi = 0, len(nums) - 1\n"
                     "    while lo <= hi:\n"
                     "        mid = (lo + hi) // 2\n"
                     "        if nums[mid] == target:\n"
                     "            return mid\n"
                     "        if nums[mid] < target:\n"
                     "            lo = mid + 1\n"
                     "        else:\n"
                     "            hi = mid - 1\n"
                     "    return -1\n",
    "merge_sorted": "def merge_sorted(a, b):\n"
                    "    i = j = 0\n"
                    "    out = []\n"
                    "    while i < len(a) and j < len(b):\n"
                    "        if a[i] <= b[j]:\n"
                    "            out.append(a[i]); i += 1\n"
                    "        else:\n"
                    "            out.append(b[j]); j += 1\n"
                    "    out.extend(a[i:])\n"
                    "    out.extend(b[j:])\n"
                    "    return out\n",
    "is_valid": "def is_valid(s):\n"
                "    pairs = {')': '(', ']': '[', '}': '{'}\n"
                "    stack = []\n"
                "    for ch in s:\n"
                "        if ch in '([{':\n"
                "            stack.append(ch)\n"
                "        elif ch in pairs:\n"
                "            if not stack or stack.pop() != pairs[ch]:\n"
                "                return False\n"
                "    return not stack\n",
    "climb_stairs": "def climb_stairs(n):\n"
                    "    a, b = 1, 1\n"
                    "    for _ in range(n):\n"
                    "        a, b = b, a + b\n"
                    "    return a\n",
    "max_profit": "def max_profit(prices):\n"
                  "    low = float('inf'); best = 0\n"
                  "    for p in prices:\n"
                  "        low = min(low, p)\n"
                  "        best = max(best, p - low)\n"
                  "    return best\n",
    "num_islands": "def num_islands(grid):\n"
                   "    if not grid: return 0\n"
                   "    rows, cols = len(grid), len(grid[0])\n"
                   "    def dfs(i, j):\n"
                   "        if i < 0 or i >= rows or j < 0 or j >= cols or grid[i][j] != 1:\n"
                   "            return\n"
                   "        grid[i][j] = 0\n"
                   "        dfs(i+1, j); dfs(i-1, j); dfs(i, j+1); dfs(i, j-1)\n"
                   "    count = 0\n"
                   "    for i in range(rows):\n"
                   "        for j in range(cols):\n"
                   "            if grid[i][j] == 1:\n"
                   "                count += 1; dfs(i, j)\n"
                   "    return count\n",
    "move_zeroes": "def move_zeroes(nums):\n"
                   "    k = 0\n"
                   "    for n in nums:\n"
                   "        if n != 0:\n"
                   "            nums[k] = n; k += 1\n"
                   "    for i in range(k, len(nums)):\n"
                   "        nums[i] = 0\n"
                   "    return nums\n",
    "merge_intervals": "def merge_intervals(intervals):\n"
                       "    if not intervals: return []\n"
                       "    intervals = sorted(intervals)\n"
                       "    out = [list(intervals[0])]\n"
                       "    for s, e in intervals[1:]:\n"
                       "        if s <= out[-1][1]:\n"
                       "            out[-1][1] = max(out[-1][1], e)\n"
                       "        else:\n"
                       "            out.append([s, e])\n"
                       "    return out\n",
    "longest_palindrome_len": "def longest_palindrome_len(s):\n"
                              "    best = 0\n"
                              "    def expand(l, r):\n"
                              "        while l >= 0 and r < len(s) and s[l] == s[r]:\n"
                              "            l -= 1; r += 1\n"
                              "        return r - l - 1\n"
                              "    for i in range(len(s)):\n"
                              "        best = max(best, expand(i, i), expand(i, i + 1))\n"
                              "    return best\n",
    "rotate_array": "def rotate_array(nums, k):\n"
                    "    if not nums: return []\n"
                    "    k %= len(nums)\n"
                    "    return nums[-k:] + nums[:-k] if k else nums[:]\n",
    "compress_string": "def compress_string(s):\n"
                       "    out = []\n"
                       "    i = 0\n"
                       "    while i < len(s):\n"
                       "        j = i\n"
                       "        while j < len(s) and s[j] == s[i]:\n"
                       "            j += 1\n"
                       "        out.append(s[i] + str(j - i))\n"
                       "        i = j\n"
                       "    return ''.join(out)\n",
    "transpose_matrix": "def transpose_matrix(m):\n"
                        "    if not m: return []\n"
                        "    return [list(row) for row in zip(*m)]\n",
    "is_subsequence": "def is_subsequence(s, t):\n"
                      "    it = iter(t)\n"
                      "    return all(ch in it for ch in s)\n",
    "gcd_number": "def gcd_number(a, b):\n"
                  "    while b:\n"
                  "        a, b = b, a % b\n"
                  "    return a\n",
    "dedupe_array": "def dedupe_array(nums):\n"
                    "    seen = set()\n"
                    "    out = []\n"
                    "    for n in nums:\n"
                    "        if n not in seen:\n"
                    "            seen.add(n); out.append(n)\n"
                    "    return out\n",
    "two_sum_sorted": "def two_sum_sorted(nums, target):\n"
                      "    i, j = 0, len(nums) - 1\n"
                      "    while i < j:\n"
                      "        s = nums[i] + nums[j]\n"
                      "        if s == target:\n"
                      "            return [i, j]\n"
                      "        if s < target:\n"
                      "            i += 1\n"
                      "        else:\n"
                      "            j -= 1\n"
                      "    return []\n",
    "max_consecutive_ones": "def max_consecutive_ones(nums):\n"
                            "    best = cur = 0\n"
                            "    for n in nums:\n"
                            "        cur = cur + 1 if n == 1 else 0\n"
                            "        best = max(best, cur)\n"
                            "    return best\n",
    "count_vowels": "def count_vowels(s):\n"
                    "    return sum(1 for ch in s.lower() if ch in 'aeiou')\n",
    "reverse_linked_list": "def reverse_linked_list(lst):\n"
                            "    return lst[::-1]\n",
    "merge_two_lists": "def merge_two_lists(a, b):\n"
                       "    return sorted(list(a) + list(b))\n",
    "count_bits": "def count_bits(n):\n"
                  "    return bin(n).count('1')\n",
    "longest_common_prefix": "def longest_common_prefix(strs):\n"
                             "    if not strs: return ''\n"
                             "    p = strs[0]\n"
                             "    for s in strs[1:]:\n"
                             "        while not s.startswith(p):\n"
                             "            p = p[:-1]\n"
                             "    return p\n",
    "intersection": "def intersection(a, b):\n"
                    "    return sorted(set(a) & set(b))\n",
    "is_power_of_two": "def is_power_of_two(n):\n"
                       "    return n > 0 and (n & (n - 1)) == 0\n",
    "tree_max_depth": "def tree_max_depth(vals):\n"
                      "    if not vals or vals[0] is None:\n"
                      "        return 0\n"
                      "    from collections import deque\n"
                      "    root = [vals[0], None, None]\n"
                      "    q = deque([root])\n"
                      "    i = 1\n"
                      "    while q and i < len(vals):\n"
                      "        node = q.popleft()\n"
                      "        if i < len(vals) and vals[i] is not None:\n"
                      "            node[1] = [vals[i], None, None]\n"
                      "            q.append(node[1])\n"
                      "        i += 1\n"
                      "        if i < len(vals) and vals[i] is not None:\n"
                      "            node[2] = [vals[i], None, None]\n"
                      "            q.append(node[2])\n"
                      "        i += 1\n"
                      "    depth = 0\n"
                      "    q = deque([(root, 1)])\n"
                      "    while q:\n"
                      "        node, d = q.popleft()\n"
                      "        depth = max(depth, d)\n"
                      "        if node[1]: q.append((node[1], d + 1))\n"
                      "        if node[2]: q.append((node[2], d + 1))\n"
                      "    return depth\n",
    "num_connected_components": "def num_connected_components(n, edges):\n"
                                "    parent = list(range(n))\n"
                                "    def find(x):\n"
                                "        while parent[x] != x:\n"
                                "            parent[x] = parent[parent[x]]\n"
                                "            x = parent[x]\n"
                                "        return x\n"
                                "    for a, b in edges:\n"
                                "        ra, rb = find(a), find(b)\n"
                                "        if ra != rb:\n"
                                "            parent[ra] = rb\n"
                                "    return len({find(i) for i in range(n)})\n",
    "house_robber": "def house_robber(nums):\n"
                    "    prev = cur = 0\n"
                    "    for n in nums:\n"
                    "        prev, cur = cur, max(cur, prev + n)\n"
                    "    return cur\n",
    "length_of_longest_substring": "def length_of_longest_substring(s):\n"
                                   "    last = {}\n"
                                   "    best = start = 0\n"
                                   "    for i, ch in enumerate(s):\n"
                                   "        if ch in last and last[ch] >= start:\n"
                                   "            start = last[ch] + 1\n"
                                   "        last[ch] = i\n"
                                   "        best = max(best, i - start + 1)\n"
                                   "    return best\n",
    "length_of_lis": "def length_of_lis(nums):\n"
                     "    if not nums: return 0\n"
                     "    dp = [1] * len(nums)\n"
                     "    for i in range(len(nums)):\n"
                     "        for j in range(i):\n"
                     "            if nums[j] < nums[i]:\n"
                     "                dp[i] = max(dp[i], dp[j] + 1)\n"
                     "    return max(dp)\n",
    "can_finish": "def can_finish(numCourses, prerequisites):\n"
                  "    from collections import deque\n"
                  "    adj = [[] for _ in range(numCourses)]\n"
                  "    indeg = [0] * numCourses\n"
                  "    for a, b in prerequisites:\n"
                  "        adj[b].append(a); indeg[a] += 1\n"
                  "    q = deque(i for i in range(numCourses) if indeg[i] == 0)\n"
                  "    seen = 0\n"
                  "    while q:\n"
                  "        u = q.popleft(); seen += 1\n"
                  "        for v in adj[u]:\n"
                  "            indeg[v] -= 1\n"
                  "            if indeg[v] == 0:\n"
                  "                q.append(v)\n"
                  "    return seen == numCourses\n",
    "valid_palindrome": "def valid_palindrome(s):\n"
                        "    t = ''.join(c.lower() for c in s if c.isalnum())\n"
                        "    return t == t[::-1]\n",
    "coin_change": "def coin_change(coins, amount):\n"
                   "    inf = float('inf')\n"
                   "    dp = [0] + [inf] * amount\n"
                   "    for i in range(1, amount + 1):\n"
                   "        for c in coins:\n"
                   "            if c <= i and dp[i - c] + 1 < dp[i]:\n"
                   "                dp[i] = dp[i - c] + 1\n"
                   "    return -1 if dp[amount] == inf else dp[amount]\n",
    "max_area": "def max_area(heights):\n"
                "    i, j = 0, len(heights) - 1\n"
                "    best = 0\n"
                "    while i < j:\n"
                "        best = max(best, (j - i) * min(heights[i], heights[j]))\n"
                "        if heights[i] < heights[j]:\n"
                "            i += 1\n"
                "        else:\n"
                "            j -= 1\n"
                "    return best\n",
    "is_isomorphic": "def is_isomorphic(s, t):\n"
                     "    if len(s) != len(t): return False\n"
                     "    m1, m2 = {}, {}\n"
                     "    for a, b in zip(s, t):\n"
                     "        if m1.setdefault(a, b) != b or m2.setdefault(b, a) != a:\n"
                     "            return False\n"
                     "    return True\n",
    "product_except_self": "def product_except_self(nums):\n"
                           "    n = len(nums)\n"
                           "    out = [1] * n\n"
                           "    p = 1\n"
                           "    for i in range(n):\n"
                           "        out[i] = p\n"
                           "        p *= nums[i]\n"
                           "    p = 1\n"
                           "    for i in range(n - 1, -1, -1):\n"
                           "        out[i] *= p\n"
                           "        p *= nums[i]\n"
                           "    return out\n",
    "max_product": "def max_product(nums):\n"
                   "    best = cur_max = cur_min = nums[0]\n"
                   "    for n in nums[1:]:\n"
                   "        cur_max, cur_min = max(n, cur_max * n, cur_min * n), min(n, cur_max * n, cur_min * n)\n"
                   "        best = max(best, cur_max)\n"
                   "    return best\n",
    "add_strings": "def add_strings(a, b):\n"
                   "    i, j, carry, out = len(a) - 1, len(b) - 1, 0, []\n"
                   "    while i >= 0 or j >= 0 or carry:\n"
                   "        s = carry + (int(a[i]) if i >= 0 else 0) + (int(b[j]) if j >= 0 else 0)\n"
                   "        out.append(str(s % 10)); carry = s // 10\n"
                   "        i -= 1; j -= 1\n"
                   "    return ''.join(reversed(out))\n",
    "spiral_order": "def spiral_order(matrix):\n"
                    "    if not matrix: return []\n"
                    "    out = []\n"
                    "    top, bottom, left, right = 0, len(matrix) - 1, 0, len(matrix[0]) - 1\n"
                    "    while top <= bottom and left <= right:\n"
                    "        for c in range(left, right + 1): out.append(matrix[top][c])\n"
                    "        top += 1\n"
                    "        for r in range(top, bottom + 1): out.append(matrix[r][right])\n"
                    "        right -= 1\n"
                    "        if top <= bottom:\n"
                    "            for c in range(right, left - 1, -1): out.append(matrix[bottom][c])\n"
                    "            bottom -= 1\n"
                    "        if left <= right:\n"
                    "            for r in range(bottom, top - 1, -1): out.append(matrix[r][left])\n"
                    "            left += 1\n"
                    "    return out\n",
    "unique_paths": "def unique_paths(m, n):\n"
                    "    dp = [1] * n\n"
                    "    for _ in range(1, m):\n"
                    "        for j in range(1, n):\n"
                    "            dp[j] += dp[j - 1]\n"
                    "    return dp[-1]\n",
    "lcs": "def lcs(a, b):\n"
           "    m, n = len(a), len(b)\n"
           "    dp = [[0] * (n + 1) for _ in range(m + 1)]\n"
           "    for i in range(1, m + 1):\n"
           "        for j in range(1, n + 1):\n"
           "            if a[i - 1] == b[j - 1]:\n"
           "                dp[i][j] = dp[i - 1][j - 1] + 1\n"
           "            else:\n"
           "                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])\n"
           "    return dp[m][n]\n",
    "edit_distance": "def edit_distance(a, b):\n"
                    "    m, n = len(a), len(b)\n"
                    "    dp = list(range(n + 1))\n"
                    "    for i in range(1, m + 1):\n"
                    "        prev = dp[0]; dp[0] = i\n"
                    "        for j in range(1, n + 1):\n"
                    "            tmp = dp[j]\n"
                    "            if a[i - 1] == b[j - 1]:\n"
                    "                dp[j] = prev\n"
                    "            else:\n"
                    "                dp[j] = min(dp[j], dp[j - 1], prev) + 1\n"
                    "            prev = tmp\n"
                    "    return dp[n]\n",
    "level_order": "def level_order(vals):\n"
                   "    if not vals or vals[0] is None: return []\n"
                   "    from collections import deque\n"
                   "    root = [vals[0], None, None]\n"
                   "    q = deque([root]); i = 1\n"
                   "    while q and i < len(vals):\n"
                   "        node = q.popleft()\n"
                   "        if i < len(vals) and vals[i] is not None:\n"
                   "            node[1] = [vals[i], None, None]; q.append(node[1])\n"
                   "        i += 1\n"
                   "        if i < len(vals) and vals[i] is not None:\n"
                   "            node[2] = [vals[i], None, None]; q.append(node[2])\n"
                   "        i += 1\n"
                   "    out = []\n"
                   "    q = deque([root])\n"
                   "    while q:\n"
                   "        level = []\n"
                   "        for _ in range(len(q)):\n"
                   "            node = q.popleft(); level.append(node[0])\n"
                   "            if node[1]: q.append(node[1])\n"
                   "            if node[2]: q.append(node[2])\n"
                   "        out.append(level)\n"
                   "    return out\n",
    "is_anagram": "def is_anagram(a, b):\n"
                  "    return sorted(a) == sorted(b)\n",
    "is_symmetric": "def is_symmetric(vals):\n"
                    "    if not vals or vals[0] is None: return True\n"
                    "    from collections import deque\n"
                    "    root = [vals[0], None, None]\n"
                    "    q = deque([root]); i = 1\n"
                    "    while q and i < len(vals):\n"
                    "        node = q.popleft()\n"
                    "        if i < len(vals) and vals[i] is not None:\n"
                    "            node[1] = [vals[i], None, None]; q.append(node[1])\n"
                    "        i += 1\n"
                    "        if i < len(vals) and vals[i] is not None:\n"
                    "            node[2] = [vals[i], None, None]; q.append(node[2])\n"
                    "        i += 1\n"
                    "    def mirror(a, b):\n"
                    "        if not a and not b: return True\n"
                    "        if not a or not b: return False\n"
                    "        return a[0] == b[0] and mirror(a[1], b[2]) and mirror(a[2], b[1])\n"
                    "    return mirror(root[1], root[2])\n",
    "count_primes": "def count_primes(n):\n"
                    "    if n < 3: return 0\n"
                    "    sieve = [True] * n\n"
                    "    sieve[0] = sieve[1] = False\n"
                    "    for i in range(2, int(n ** 0.5) + 1):\n"
                    "        if sieve[i]:\n"
                    "            for j in range(i * i, n, i):\n"
                    "                sieve[j] = False\n"
                    "    return sum(sieve)\n",
    "single_number": "def single_number(nums):\n"
                     "    r = 0\n"
                     "    for n in nums:\n"
                     "        r ^= n\n"
                     "    return r\n",
    "reverse_words": "def reverse_words(s):\n"
                     "    return ' '.join(reversed(s.split()))\n",
    "majority_element": "def majority_element(nums):\n"
                        "    cand = count = 0\n"
                        "    for n in nums:\n"
                        "        if count == 0:\n"
                        "            cand = n\n"
                        "        count += 1 if n == cand else -1\n"
                        "    return cand\n",
    "island_perimeter": "def island_perimeter(grid):\n"
                        "    if not grid: return 0\n"
                        "    rows, cols = len(grid), len(grid[0])\n"
                        "    p = 0\n"
                        "    for i in range(rows):\n"
                        "        for j in range(cols):\n"
                        "            if grid[i][j] == 1:\n"
                        "                p += 4\n"
                        "                if i > 0 and grid[i-1][j] == 1: p -= 2\n"
                        "                if j > 0 and grid[i][j-1] == 1: p -= 2\n"
                        "    return p\n",
    "is_palindrome_number": "def is_palindrome_number(x):\n"
                            "    s = str(x)\n"
                            "    return s == s[::-1]\n",
    "length_of_last_word": "def length_of_last_word(s):\n"
                           "    return len(s.split()[-1]) if s.split() else 0\n",
    "missing_number": "def missing_number(nums):\n"
                      "    n = len(nums)\n"
                      "    return n * (n + 1) // 2 - sum(nums)\n",
    "minimum_total": "def minimum_total(triangle):\n"
                     "    dp = triangle[-1][:]\n"
                     "    for i in range(len(triangle) - 2, -1, -1):\n"
                     "        for j in range(len(triangle[i])):\n"
                     "            dp[j] = triangle[i][j] + min(dp[j], dp[j + 1])\n"
                     "    return dp[0]\n",
    "detect_capital": "def detect_capital(word):\n"
                      "    return word.isupper() or word.islower() or (word[:1].isupper() and word[1:].islower())\n",
    "third_max": "def third_max(nums):\n"
                 "    uniq = sorted(set(nums), reverse=True)\n"
                 "    return uniq[2] if len(uniq) >= 3 else uniq[0]\n",
    "array_pair_sum": "def array_pair_sum(nums):\n"
                      "    return sum(sorted(nums)[::2])\n",
}

JUDGE_MARK = "请严格按下面的 JSON 结构输出"


def build_reply(user_text: str) -> str:
    if JUDGE_MARK in user_text:
        rubric = user_text.split("【评分要点】", 2)[-1].split("【参考答案")[0]
        n = len(re.findall(r"(?m)^\s*\d+\.\s", rubric)) or 1
        points = [{"point": f"要点{i + 1}", "score": 0.5, "reason": "mock 裁判给分"}
                  for i in range(n)]
        return json.dumps({"points": points, "total_comment": "mock 裁判评语"}, ensure_ascii=False)

    m = re.search(r"函数名必须为\s*`(\w+)`", user_text)
    if m:
        name = m.group(1)
        code = CODE_IMPLS.get(name, "def solve(*args):\n    return None\n")
        return "下面是实现：\n```python\n" + code + "```\n"

    if "单项选择题" in user_text:
        return "先分析各选项，排除明显错误项。\n最终选择：\n【答案】A"

    if "多项选择题" in user_text:
        return "逐项分析后，正确选项为 A、B、D。\n【答案】ABD"

    if "判断下面的陈述" in user_text:
        return "该陈述与事实不符，存在反例。\n【答案】错"

    if "填空题" in user_text:
        return "根据题意逐步推导。\n【答案】1"

    # solution / interview
    return ("这是一个 mock 回答。\n\n"
            "1. 先说明问题的核心概念。\n"
            "2. 再给出关键步骤与结论。\n"
            "3. 最后做简短总结。")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:  # noqa: BLE001
            body = {}
        messages = body.get("messages") or []
        user_text = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_text = msg.get("content") or ""
                break
        reply = build_reply(user_text)
        out = {
            "id": "mock-1",
            "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": reply},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }
        raw = json.dumps(out, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):  # noqa: N802
        if self.path.rstrip("/") in ("/v1/models", "/models"):
            raw = json.dumps({"data": [{"id": "mock"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        else:
            self.send_response(404)
            self.end_headers()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=18080)
    args = p.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"mock model on http://{args.host}:{args.port}/v1")
    srv.serve_forever()


if __name__ == "__main__":
    main()

# 逻辑错误提取器详细讲解

## 概述

`logic_error_extractor.py` 是一个专门从**结构化推理过程**中提取逻辑错误的工具。它依赖于标准化的推理格式（如我们在 `logic_agent_zebralogic.yaml` 中定义的格式），通过解析推理步骤、提取断言、检测逻辑冲突来识别错误。

## 整体架构

脚本包含三个核心组件：

1. **StructuredReasoningParser** - 解析结构化的推理过程
2. **LogicErrorExtractor** - 提取四种类型的逻辑错误
3. **EnhancedLogicErrorAnalyzer** - 整合分析器，提供统一接口

```
推理文本 → Parser → 结构化步骤 → ErrorExtractor → 错误列表
                                    ↓
                              四种错误检测
```

---

## 第一部分：推理过程解析器 (StructuredReasoningParser)

### 功能：将自然语言推理转换为结构化数据

#### 1. 解析推理步骤 (`parse_reasoning_steps`)

```python
def parse_reasoning_steps(self, response: str) -> List[Dict[str, Any]]:
```

**作用**：从模型响应中提取结构化的推理步骤

**代码解析**：

```31:70:utu/practice/verify/logic_error_extractor.py
    def parse_reasoning_steps(self, response: str) -> List[Dict[str, Any]]:
        """
        解析推理步骤
        
        Returns:
            List of steps, each with:
            - step_num: 步骤编号
            - text: 步骤文本
            - clue_refs: 引用的线索编号
            - assertions: 提取的断言
        """
        # 提取<answer>之前的推理内容
        answer_match = re.search(r'<answer>', response, re.IGNORECASE)
        reasoning_text = response[:answer_match.start()] if answer_match else response
        
        steps = []
        
        # 匹配步骤：支持 "1.", "步骤1:", "Step 1:"
        step_pattern = r'(?:^|\n)\s*(?:(\d+)[\.\)]|(?:步骤|Step)\s*(\d+)[:\s])\s*(.+?)(?=(?:\n\s*(?:\d+[\.\)]|(?:步骤|Step)\s*\d+)|\n\n|$))'
        
        matches = re.finditer(step_pattern, reasoning_text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        for match in matches:
            step_num = match.group(1) or match.group(2)
            step_text = match.group(3).strip()
            
            # 提取线索引用
            clue_refs = self._extract_clue_references(step_text)
            
            # 提取断言
            assertions = self._extract_assertions(step_text)
            
            steps.append({
                "step_num": int(step_num) if step_num else None,
                "text": step_text,
                "clue_refs": clue_refs,
                "assertions": assertions,
            })
        
        return steps
```

**关键点**：
- 使用正则表达式匹配步骤编号（`1.`, `步骤1:`, `Step 1:`）
- 提取 `<answer>` 标签之前的内容作为推理过程
- 每个步骤包含：编号、文本、线索引用、断言

**示例输入**：
```
1. From clue 1, Peter is in house 1.
2. From clue 2, Alice is in house 2.
3. Therefore, Peter and Alice are in different houses.
```

**解析结果**：
```python
[
    {
        "step_num": 1,
        "text": "From clue 1, Peter is in house 1.",
        "clue_refs": [1],
        "assertions": [{"type": "person_in_house", "entity": "Peter", "value": "1"}]
    },
    {
        "step_num": 2,
        "text": "From clue 2, Alice is in house 2.",
        "clue_refs": [2],
        "assertions": [{"type": "person_in_house", "entity": "Alice", "value": "2"}]
    },
    # ...
]
```

#### 2. 提取线索引用 (`_extract_clue_references`)

```72:92:utu/practice/verify/logic_error_extractor.py
    def _extract_clue_references(self, text: str) -> List[int]:
        """提取线索引用编号"""
        clue_refs = []
        
        # 匹配 "clue 1", "线索1", "constraint 2" 等
        patterns = [
            r'clue\s*(\d+)',
            r'线索\s*(\d+)',
            r'constraint\s*(\d+)',
            r'约束\s*(\d+)',
            r'条件\s*(\d+)',
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                clue_num = int(match.group(1))
                if clue_num not in clue_refs:
                    clue_refs.append(clue_num)
        
        return sorted(clue_refs)
```

**作用**：识别步骤中引用的线索编号，用于检测未使用的线索

#### 3. 提取断言 (`_extract_assertions`)

```94:141:utu/practice/verify/logic_error_extractor.py
    def _extract_assertions(self, text: str) -> List[Dict[str, str]]:
        """
        提取断言（赋值语句）
        
        Returns:
            List of assertions with entity, attribute, value
        """
        assertions = []
        
        # 模式1: "X is in house Y"
        pattern1 = r'(\w+(?:\s+\w+)?)\s+is\s+(?:in|located in)\s+house\s+(\d+)'
        for match in re.finditer(pattern1, text, re.IGNORECASE):
            assertions.append({
                "type": "person_in_house",
                "entity": match.group(1).strip(),
                "value": match.group(2).strip(),
                "text": match.group(0)
            })
        
        # 模式2: "House X has Y" 或 "House X contains Y"
        pattern2 = r'house\s+(\d+)\s+(?:has|contains|owns)\s+(?:(?:a|the)\s+)?(\w+(?:\s+\w+)*)'
        for match in re.finditer(pattern2, text, re.IGNORECASE):
            house = match.group(1).strip()
            attr_value = match.group(2).strip()
            assertions.append({
                "type": "house_has_attribute",
                "entity": f"house_{house}",
                "attribute": self._guess_attribute_type(attr_value),
                "value": attr_value,
                "text": match.group(0)
            })
        
        # 模式3: "X has Y" 或 "X owns Y"
        pattern3 = r'(\w+(?:\s+\w+)?)\s+(?:has|owns|possesses)\s+(?:(?:a|the)\s+)?(\w+(?:\s+\w+)*)'
        for match in re.finditer(pattern3, text, re.IGNORECASE):
            entity = match.group(1).strip()
            attr_value = match.group(2).strip()
            # 排除 "house has" 的情况（已在模式2处理）
            if entity.lower() != "house":
                assertions.append({
                    "type": "entity_has_attribute",
                    "entity": entity,
                    "attribute": self._guess_attribute_type(attr_value),
                    "value": attr_value,
                    "text": match.group(0)
                })
        
        return assertions
```

**作用**：从文本中提取三种类型的断言：
1. **person_in_house**: "Peter is in house 1"
2. **house_has_attribute**: "House 1 has color red"
3. **entity_has_attribute**: "Peter has pet bird"

---

## 第二部分：错误类型详解

### 错误类型1：矛盾 (Contradictions)

#### 检测逻辑

```261:320:utu/practice/verify/logic_error_extractor.py
    def _detect_contradictions(self, steps: List[Dict]) -> List[str]:
        """检测推理中的矛盾"""
        contradictions = []
        
        # 收集所有的人-房子赋值
        person_assignments = {}  # person -> list of houses
        
        for step in steps:
            for assertion in step["assertions"]:
                if assertion["type"] == "person_in_house":
                    person = assertion["entity"].lower()
                    house = assertion["value"]
                    
                    if person not in person_assignments:
                        person_assignments[person] = []
                    person_assignments[person].append({
                        "house": house,
                        "step": step["step_num"],
                        "text": assertion["text"]
                    })
        
        # 检测矛盾：同一个人被分配到不同房子
        for person, assignments in person_assignments.items():
            if len(assignments) > 1:
                # 检查是否都是同一个房子
                houses = set(a["house"] for a in assignments)
                if len(houses) > 1:
                    steps_involved = [a["step"] for a in assignments]
                    contradictions.append(
                        f"矛盾：{person.capitalize()} 在步骤 {steps_involved} 中被分配到不同房子 {list(houses)}"
                    )
        
        # 收集所有的房子-属性赋值
        house_attributes = defaultdict(lambda: defaultdict(list))  # house -> attribute -> values
        
        for step in steps:
            for assertion in step["assertions"]:
                if assertion["type"] == "house_has_attribute":
                    house = assertion["entity"]
                    attr_type = assertion.get("attribute", "unknown")
                    value = assertion["value"].lower()
                    
                    house_attributes[house][attr_type].append({
                        "value": value,
                        "step": step["step_num"],
                        "text": assertion["text"]
                    })
        
        # 检测矛盾：同一个房子的同一属性有多个不同值
        for house, attributes in house_attributes.items():
            for attr_type, values_list in attributes.items():
                if len(values_list) > 1:
                    unique_values = set(v["value"] for v in values_list)
                    if len(unique_values) > 1:
                        steps_involved = [v["step"] for v in values_list]
                        contradictions.append(
                            f"矛盾：{house} 的 {attr_type} 在步骤 {steps_involved} 中有不同值 {list(unique_values)}"
                        )
        
        return contradictions
```

#### 检测两种矛盾：

**1. 人员位置矛盾**
- **问题**：同一个人被分配到不同的房子
- **示例**：
  ```
  步骤1: Peter is in house 1.
  步骤3: Peter is in house 2.  ← 矛盾！
  ```
- **检测逻辑**：
  1. 收集所有 `person_in_house` 断言
  2. 按人员分组，检查每个人是否被分配到多个不同房子
  3. 如果发现，记录涉及的步骤和房子

**2. 属性值矛盾**
- **问题**：同一个房子的同一属性有多个不同值
- **示例**：
  ```
  步骤2: House 1 has color red.
  步骤5: House 1 has color blue.  ← 矛盾！
  ```
- **检测逻辑**：
  1. 收集所有 `house_has_attribute` 断言
  2. 按房子和属性类型分组
  3. 检查同一属性的值是否唯一
  4. 如果发现多个不同值，记录矛盾

---

### 错误类型2：约束违反 (Constraint Violations)

#### 检测逻辑

```322:356:utu/practice/verify/logic_error_extractor.py
    def _detect_constraint_violations(self, steps: List[Dict], ground_truth: Dict = None) -> List[str]:
        """检测约束违反（主要是唯一性约束）"""
        violations = []
        
        # 收集所有属性的使用情况
        attribute_usage = defaultdict(list)  # value -> list of (house, step)
        
        for step in steps:
            for assertion in step["assertions"]:
                if assertion["type"] == "house_has_attribute":
                    house = assertion["entity"]
                    value = assertion["value"].lower()
                    attr_type = assertion.get("attribute", "unknown")
                    
                    # 排除 house 编号本身
                    if attr_type != "unknown":
                        key = f"{attr_type}:{value}"
                        attribute_usage[key].append({
                            "house": house,
                            "step": step["step_num"],
                            "text": assertion["text"]
                        })
        
        # 检测唯一性约束违反：同一属性值被分配给多个房子
        for key, usage_list in attribute_usage.items():
            if len(usage_list) > 1:
                houses = set(u["house"] for u in usage_list)
                if len(houses) > 1:
                    attr_type, value = key.split(":", 1)
                    steps_involved = [u["step"] for u in usage_list]
                    violations.append(
                        f"唯一性约束违反：{attr_type} '{value}' 在步骤 {steps_involved} 中被分配给多个房子 {list(houses)}"
                    )
        
        return violations
```

#### 检测唯一性约束违反

**问题**：同一属性值被分配给多个房子（违反唯一性约束）

**示例**：
```
步骤2: House 1 has color red.
步骤4: House 2 has color red.  ← 违反唯一性约束！每个颜色只能分配给一个房子
```

**检测逻辑**：
1. 收集所有属性赋值，按 `属性类型:值` 分组
2. 检查每个属性值是否被分配给多个房子
3. 如果发现，记录违反的约束和涉及的步骤

**关键区别**：
- **矛盾**：同一个实体有多个不同值（如 House 1 同时有 red 和 blue）
- **约束违反**：同一个值被分配给多个实体（如 red 同时分配给 House 1 和 House 2）

---

### 错误类型3：推理跳跃 (Reasoning Gaps)

#### 检测逻辑

```358:391:utu/practice/verify/logic_error_extractor.py
    def _detect_reasoning_gaps(self, steps: List[Dict]) -> List[str]:
        """检测推理跳跃或缺失的逻辑连接"""
        gaps = []
        
        # 检查是否有推理步骤缺少线索引用
        steps_without_clues = []
        for step in steps:
            # 跳过结论性步骤（包含 therefore, 因此 等）
            is_conclusion = any(
                keyword in step["text"].lower() 
                for keyword in ["therefore", "thus", "hence", "因此", "所以", "从而"]
            )
            
            # 如果不是结论且没有引用线索，可能是推理跳跃
            if not is_conclusion and not step["clue_refs"] and step["assertions"]:
                steps_without_clues.append(step["step_num"])
        
        if steps_without_clues:
            gaps.append(
                f"推理跳跃：步骤 {steps_without_clues} 做出了断言但没有引用具体线索"
            )
        
        # 检查推理链条的连续性
        if len(steps) > 0:
            step_nums = [s["step_num"] for s in steps if s["step_num"]]
            if step_nums:
                # 检查步骤编号是否连续
                for i in range(len(step_nums) - 1):
                    if step_nums[i+1] - step_nums[i] > 1:
                        gaps.append(
                            f"推理链条不连续：步骤 {step_nums[i]} 到 {step_nums[i+1]} 之间有跳跃"
                        )
        
        return gaps
```

#### 检测两种推理跳跃：

**1. 缺少线索引用的步骤**
- **问题**：步骤做出了断言但没有引用具体线索
- **示例**：
  ```
  步骤1: From clue 1, Peter is in house 1.  ✓ 有线索引用
  步骤2: Alice is in house 2.  ← 缺少线索引用！不知道依据是什么
  ```
- **检测逻辑**：
  1. 检查每个步骤是否有线索引用
  2. 排除结论性步骤（包含 "therefore", "因此" 等）
  3. 如果非结论步骤有断言但无线索引用，标记为推理跳跃

**2. 步骤编号不连续**
- **问题**：推理步骤编号跳跃，可能遗漏了中间步骤
- **示例**：
  ```
  步骤1: ...
  步骤2: ...
  步骤5: ...  ← 步骤3和4去哪了？
  ```
- **检测逻辑**：
  1. 检查步骤编号是否连续
  2. 如果发现跳跃（如从步骤2直接跳到步骤5），记录为推理链条不连续

---

### 错误类型4：未使用的线索 (Unused Clues)

#### 检测逻辑

```393:425:utu/practice/verify/logic_error_extractor.py
    def _detect_unused_clues(self, steps: List[Dict], question: str) -> List[str]:
        """检测未使用的线索"""
        unused = []
        
        # 从问题中提取总共有多少条线索
        # 假设线索以 "Clue 1:", "线索1:", "1." 等开头
        clue_pattern = r'(?:clue|线索|约束)\s*(\d+)'
        question_clues = set()
        for match in re.finditer(clue_pattern, question, re.IGNORECASE):
            question_clues.add(int(match.group(1)))
        
        # 如果找不到编号的线索，尝试计数
        if not question_clues:
            # 计算有多少个以数字开头的行（可能是线索）
            numbered_lines = re.findall(r'(?:^|\n)\s*(\d+)[\.\)]', question, re.MULTILINE)
            if numbered_lines:
                max_clue = max(int(n) for n in numbered_lines)
                question_clues = set(range(1, max_clue + 1))
        
        # 收集使用过的线索
        used_clues = set()
        for step in steps:
            used_clues.update(step["clue_refs"])
        
        # 找出未使用的线索
        if question_clues and used_clues:
            missing_clues = question_clues - used_clues
            if missing_clues:
                unused.append(
                    f"未使用线索：线索 {sorted(missing_clues)} 在推理过程中未被引用"
                )
        
        return unused
```

#### 检测未使用的线索

**问题**：问题中提供了线索，但推理过程中没有使用

**示例**：
```
问题：
Clue 1: Peter is in house 1.
Clue 2: Alice is in house 2.
Clue 3: House 1 has color red.

推理：
步骤1: From clue 1, Peter is in house 1.
步骤2: From clue 2, Alice is in house 2.
← 线索3没有被使用！
```

**检测逻辑**：
1. 从问题文本中提取所有线索编号
2. 从推理步骤中收集所有使用的线索
3. 计算差集，找出未使用的线索
4. 如果发现未使用的线索，记录警告

**重要性**：未使用的线索可能导致不完整的推理或错误答案

---

## 第三部分：错误提取流程

### 主流程 (`extract_errors`)

```180:259:utu/practice/verify/logic_error_extractor.py
    def extract_errors(self, sample: EvaluationSample, ground_truth_parsed: Dict = None) -> Dict[str, Any]:
        """
        提取推理过程中的错误
        
        Args:
            sample: EvaluationSample
            ground_truth_parsed: 解析后的正确答案（可选，用于更准确的错误检测）
        
        Returns:
            Dict with:
            - has_errors: bool
            - errors: List of error descriptions
            - error_types: Dict of errors by type
            - summary: 简洁的错误总结
        """
        response = sample.response
        
        if not response:
            return {
                "has_errors": False,
                "errors": [],
                "error_types": {},
                "summary": None
            }
        
        # 解析推理步骤
        steps = self.parser.parse_reasoning_steps(response)
        
        if not steps:
            return {
                "has_errors": True,
                "errors": ["无法解析推理步骤，可能缺少步骤编号"],
                "error_types": {"parsing_error": ["推理格式不规范"]},
                "summary": "推理格式不规范，无法解析步骤"
            }
        
        # 收集所有错误
        all_errors = []
        error_types = defaultdict(list)
        
        # 1. 检测矛盾
        contradictions = self._detect_contradictions(steps)
        if contradictions:
            all_errors.extend(contradictions)
            error_types["contradictions"] = contradictions
        
        # 2. 检测约束违反
        constraint_violations = self._detect_constraint_violations(steps, ground_truth_parsed)
        if constraint_violations:
            all_errors.extend(constraint_violations)
            error_types["constraint_violations"] = constraint_violations
        
        # 3. 检测推理跳跃/缺失推理
        reasoning_gaps = self._detect_reasoning_gaps(steps)
        if reasoning_gaps:
            all_errors.extend(reasoning_gaps)
            error_types["reasoning_gaps"] = reasoning_gaps
        
        # 4. 检测未使用的线索
        unused_clues = self._detect_unused_clues(steps, sample.raw_question)
        if unused_clues:
            all_errors.extend(unused_clues)
            error_types["unused_clues"] = unused_clues
        
        # 生成总结
        if all_errors:
            summary = self._generate_error_summary(error_types)
            return {
                "has_errors": True,
                "errors": all_errors,
                "error_types": dict(error_types),
                "summary": summary
            }
        else:
            return {
                "has_errors": False,
                "errors": [],
                "error_types": {},
                "summary": None
            }
```

**流程**：
1. 解析推理步骤
2. 依次检测四种错误类型
3. 汇总所有错误
4. 生成错误总结

---

## 第四部分：输出格式

### 错误总结生成

```427:443:utu/practice/verify/logic_error_extractor.py
    def _generate_error_summary(self, error_types: Dict[str, List[str]]) -> str:
        """生成简洁的错误总结"""
        summary_parts = []
        
        if error_types.get("contradictions"):
            summary_parts.append(f"发现 {len(error_types['contradictions'])} 个矛盾")
        
        if error_types.get("constraint_violations"):
            summary_parts.append(f"发现 {len(error_types['constraint_violations'])} 个约束违反")
        
        if error_types.get("reasoning_gaps"):
            summary_parts.append(f"发现 {len(error_types['reasoning_gaps'])} 个推理跳跃")
        
        if error_types.get("unused_clues"):
            summary_parts.append(f"有线索未使用")
        
        return "；".join(summary_parts) if summary_parts else "未检测到明显错误"
```

### 示例输出

```python
{
    "has_errors": True,
    "errors": [
        "矛盾：Peter 在步骤 [1, 3] 中被分配到不同房子 ['1', '2']",
        "唯一性约束违反：color 'red' 在步骤 [2, 5] 中被分配给多个房子 ['house_1', 'house_2']",
        "推理跳跃：步骤 [4] 做出了断言但没有引用具体线索",
        "未使用线索：线索 [3] 在推理过程中未被引用"
    ],
    "error_types": {
        "contradictions": ["矛盾：Peter 在步骤 [1, 3] 中被分配到不同房子 ['1', '2']"],
        "constraint_violations": ["唯一性约束违反：color 'red' 在步骤 [2, 5] 中被分配给多个房子 ['house_1', 'house_2']"],
        "reasoning_gaps": ["推理跳跃：步骤 [4] 做出了断言但没有引用具体线索"],
        "unused_clues": ["未使用线索：线索 [3] 在推理过程中未被引用"]
    },
    "summary": "发现 1 个矛盾；发现 1 个约束违反；发现 1 个推理跳跃；有线索未使用"
}
```

---

## 使用场景

### 1. 在验证函数中使用

```486:545:utu/practice/verify/logic_error_extractor.py
def verify_func(sample: EvaluationSample, timeout_score: float = 0, **kwargs) -> dict:
    """
    增强的验证函数，使用逻辑错误提取 (V3)
    
    改进：
    - 从结构化推理过程中提取具体的逻辑错误
    - 检测矛盾、约束违反、推理跳跃
    - 生成可供 LLM 学习的错误描述
    
    Args:
        sample: EvaluationSample
        timeout_score: Score to return on timeout
        **kwargs: Additional arguments
            - enable_error_extraction: Whether to extract errors (default: True)
            - include_steps: Include parsed steps in result (default: False)
    
    Returns:
        Dictionary with:
        - 'reward' (float): Score
        - 'reasoning' (str or None): Error summary for incorrect answers
    """
    # Get standard verification result
    result = original_verify_func(sample, timeout_score, **kwargs)
    
    # Check if error extraction should be performed
    enable_error_extraction = kwargs.get("enable_error_extraction", True)
    
    # If answer is correct, no need for error analysis
    if result["reward"] >= 1.0:
        return result
    
    # If error extraction is disabled, return standard result
    if not enable_error_extraction:
        return result
    
    # Extract errors from reasoning process
    try:
        analyzer = EnhancedLogicErrorAnalyzer()
        analysis = analyzer.analyze(sample)
        
        if analysis["has_errors"] and analysis["errors"]:
            # 格式化错误信息用于 critique
            error_lines = []
            for i, error in enumerate(analysis["errors"][:5], 1):  # 最多5个错误
                error_lines.append(f"{i}. {error}")
            
            result["reasoning"] = "推理过程中的错误：\n" + "\n".join(error_lines)
        else:
            result["reasoning"] = analysis["error_summary"]
        
        # 可选：包含详细的错误类型
        if kwargs.get("include_error_details", False):
            result["error_details"] = analysis
            
    except Exception as e:
        # If error extraction fails, log warning but don't fail the verification
        logger.warning(f"Error during error extraction: {e}", exc_info=True)
        result["reasoning"] = "答案不正确（错误提取失败）"
    
    return result
```

### 2. 独立使用

```548:561:utu/practice/verify/logic_error_extractor.py
def extract_errors_standalone(sample: EvaluationSample) -> Dict[str, Any]:
    """
    独立的错误提取函数（不验证答案）
    
    用于在 Training-Free GRPO 流程中单独调用
    
    Args:
        sample: EvaluationSample with response
    
    Returns:
        错误分析结果
    """
    analyzer = EnhancedLogicErrorAnalyzer()
    return analyzer.analyze(sample)
```

---

## 总结

`logic_error_extractor.py` 能够提取四种类型的推理错误：

1. **矛盾** - 同一实体被赋予不同的值
2. **约束违反** - 违反唯一性约束（同一值分配给多个实体）
3. **推理跳跃** - 缺少线索引用或步骤不连续
4. **未使用的线索** - 问题中的线索未被使用

这些错误信息会被传递给经验生成器，帮助模型学习如何避免类似的错误。



















































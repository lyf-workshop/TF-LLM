"""
逻辑冲突检测和经验总结脚本

功能：
1. 检测推理过程中的逻辑冲突（矛盾、约束违反、不一致等）
2. 从冲突中提取经验教训
3. 生成可用的经验总结，帮助大模型改进推理

使用方式：
    # 单个样本分析
    python scripts/logic_conflict_detector.py --sample <sample_json>
    
    # 批量分析
    python scripts/logic_conflict_detector.py --batch <samples_file.json>
    
    # 从数据库分析
    python scripts/logic_conflict_detector.py --dataset <dataset_name> --limit 100
"""

import argparse
import asyncio
import json
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from utu.db import EvaluationSample
from utu.utils import SimplifiedAsyncOpenAI, get_logger
from utu.config import ConfigLoader

logger = get_logger(__name__)


class LogicConflictDetector:
    """
    逻辑冲突检测器
    
    检测类型：
    1. 直接矛盾：同一实体被赋予不同的值
    2. 约束违反：违反了问题中的约束条件
    3. 循环推理：使用已排除的可能性
    4. 不一致推理：前后推理步骤不一致
    5. 重复分配：同一属性被分配给多个实体
    """
    
    def __init__(self, llm: Optional[SimplifiedAsyncOpenAI] = None):
        self.llm = llm
        
    def detect_conflicts(self, sample: EvaluationSample) -> Dict[str, Any]:
        """
        检测样本中的所有逻辑冲突
        
        Args:
            sample: EvaluationSample containing question, response, and ground truth
            
        Returns:
            Dict with conflict analysis results
        """
        response = sample.response or ""
        question = sample.raw_question or ""
        
        # 提取推理步骤
        reasoning_steps = self._extract_reasoning_steps(response)
        
        # 检测各种冲突
        conflicts = {
            "contradictions": self._detect_contradictions(reasoning_steps),
            "constraint_violations": self._detect_constraint_violations(response, question),
            "circular_reasoning": self._detect_circular_reasoning(reasoning_steps),
            "inconsistent_assignments": self._detect_inconsistent_assignments(response),
            "duplicate_assignments": self._detect_duplicate_assignments(response),
        }
        
        # 统计信息
        total_conflicts = sum(len(v) for v in conflicts.values())
        
        return {
            "has_conflicts": total_conflicts > 0,
            "total_conflicts": total_conflicts,
            "conflicts_by_type": conflicts,
            "reasoning_steps": reasoning_steps,
            "summary": self._generate_conflict_summary(conflicts),
        }
    
    def _extract_reasoning_steps(self, response: str) -> List[str]:
        """提取推理步骤"""
        steps = []
        
        # 提取<answer>之前的内容作为推理过程
        answer_match = re.search(r'<answer>', response, re.IGNORECASE)
        if answer_match:
            reasoning_text = response[:answer_match.start()]
        else:
            reasoning_text = response
        
        # 按步骤标记分割
        step_patterns = [
            r'(?:^|\n)\s*(?:\d+[\.\)]|步骤\s*\d+|Step\s+\d+)\s+(.+?)(?=(?:^|\n)\s*(?:\d+[\.\)]|步骤\s*\d+|Step\s+\d+)|$)',
            r'(?:^|\n)\s*[-*]\s+(.+?)(?=(?:^|\n)\s*[-*]|$)',
        ]
        
        for pattern in step_patterns:
            matches = re.findall(pattern, reasoning_text, re.MULTILINE | re.DOTALL)
            if matches:
                steps = [m.strip() for m in matches if m.strip()]
                break
        
        # 如果没有找到步骤标记，按段落分割
        if not steps:
            paragraphs = [p.strip() for p in reasoning_text.split('\n\n') if p.strip()]
            steps = paragraphs[:10]  # 最多取10段
        
        return steps
    
    def _detect_contradictions(self, reasoning_steps: List[str]) -> List[Dict]:
        """
        检测直接矛盾
        
        例如：
        - "Peter is in house 1" 和 "Peter is in house 2"
        - "House 1 has color red" 和 "House 1 has color blue"
        """
        contradictions = []
        
        # 提取所有断言
        assertions = []
        for i, step in enumerate(reasoning_steps):
            step_assertions = self._extract_assertions(step)
            for assertion in step_assertions:
                assertions.append((i, assertion))
        
        # 检查矛盾
        for i, (step_idx1, assertion1) in enumerate(assertions):
            for step_idx2, assertion2 in assertions[i+1:]:
                if self._are_contradicting(assertion1, assertion2):
                    contradictions.append({
                        "type": "contradiction",
                        "step1": step_idx1 + 1,
                        "step2": step_idx2 + 1,
                        "assertion1": assertion1,
                        "assertion2": assertion2,
                        "description": f"步骤 {step_idx1 + 1} 和步骤 {step_idx2 + 1} 存在矛盾",
                    })
        
        return contradictions
    
    def _extract_assertions(self, step: str) -> List[str]:
        """从推理步骤中提取断言"""
        assertions = []
        
        # 模式1: "X is/has Y" 或 "X in house Y"
        patterns = [
            # 英文模式
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:is|has|owns)\s+([a-z]+(?:\s+[a-z]+)?)",
            r"([A-Z][a-z]+)\s+in\s+(?:house|position)\s+(\d+)",
            r"House\s+(\d+)\s+has\s+([a-z]+(?:\s+[a-z]+)?)",
            r"([A-Z][a-z]+)\s+is\s+in\s+house\s+(\d+)",
            # 中文模式
            r"([\u4e00-\u9fa5]+)\s+(?:在|位于|是)\s+(?:房子|房屋)\s*(\d+)",
            r"房子\s*(\d+)\s+(?:有|是|属于)\s+([\u4e00-\u9fa5]+)",
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, step, re.IGNORECASE)
            for match in matches:
                if len(match) == 2:
                    entity, value = match
                    assertions.append(f"{entity.strip()} -> {value.strip()}")
        
        return assertions
    
    def _are_contradicting(self, assertion1: str, assertion2: str) -> bool:
        """检查两个断言是否矛盾"""
        if "->" not in assertion1 or "->" not in assertion2:
            return False
        
        entity1, value1 = assertion1.split("->", 1)
        entity2, value2 = assertion2.split("->", 1)
        
        entity1 = entity1.strip().lower()
        entity2 = entity2.strip().lower()
        value1 = value1.strip().lower()
        value2 = value2.strip().lower()
        
        # 相同实体，不同值
        if entity1 == entity2 and value1 != value2:
            # 检查是否是同一类型的属性（避免误报）
            # 简单启发式：如果值都是数字，可能是位置冲突
            if value1.isdigit() and value2.isdigit():
                return True
            # 如果值都是颜色/名称等，可能是属性冲突
            if not value1.isdigit() and not value2.isdigit():
                return True
        
        return False
    
    def _detect_constraint_violations(self, response: str, question: str) -> List[Dict]:
        """
        检测约束违反
        
        检查推理过程中是否违反了问题中提到的约束条件
        """
        violations = []
        
        # 提取问题中的约束（线索）
        clue_patterns = [
            r"clue\s+(\d+)[:：]?\s*(.+?)(?=clue\s+\d+|$)",
            r"线索\s*(\d+)[:：]?\s*(.+?)(?=线索\s*\d+|$)",
            r"constraint\s+(\d+)[:：]?\s*(.+?)(?=constraint\s+\d+|$)",
            r"约束\s*(\d+)[:：]?\s*(.+?)(?=约束\s*\d+|$)",
        ]
        
        clues = []
        for pattern in clue_patterns:
            matches = re.findall(pattern, question, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                clues.append({"num": match[0], "content": match[1].strip()})
        
        # 检查推理过程中是否违反了约束
        # 这里使用简单的启发式方法
        # 更复杂的检测可以使用LLM或更详细的规则
        
        return violations
    
    def _detect_circular_reasoning(self, reasoning_steps: List[str]) -> List[Dict]:
        """
        检测循环推理
        
        例如：使用已排除的可能性，或循环引用
        """
        circular = []
        
        # 跟踪已排除的可能性
        eliminated = set()
        used = set()
        
        for i, step in enumerate(reasoning_steps):
            # 查找排除语句
            elim_patterns = [
                r"(?:cannot|can't|not|isn't|aren't|排除|不能|不是)\s+(?:be|have|是|有)?\s*([a-z\u4e00-\u9fa5\s]+)",
                r"eliminate[ds]?\s+([a-z\u4e00-\u9fa5\s]+)",
                r"rule[ds]?\s+out\s+([a-z\u4e00-\u9fa5\s]+)",
            ]
            
            for pattern in elim_patterns:
                matches = re.findall(pattern, step, re.IGNORECASE)
                for match in matches:
                    eliminated.add(match.strip().lower())
            
            # 查找使用语句
            use_patterns = [
                r"(?:must|has to|is|are|have|必须|是|有)\s+(?:be|have)?\s*([a-z\u4e00-\u9fa5\s]+)",
                r"assign[ed]?\s+([a-z\u4e00-\u9fa5\s]+)",
            ]
            
            for pattern in use_patterns:
                matches = re.findall(pattern, step, re.IGNORECASE)
                for match in matches:
                    used.add(match.strip().lower())
        
        # 检查冲突
        conflicts = eliminated.intersection(used)
        for conflict in conflicts:
            circular.append({
                "type": "circular_reasoning",
                "item": conflict,
                "description": f"项目 '{conflict}' 被排除但后续又被使用",
            })
        
        return circular
    
    def _detect_inconsistent_assignments(self, response: str) -> List[Dict]:
        """
        检测不一致的赋值
        
        例如：在推理过程中多次改变同一实体的属性
        """
        inconsistencies = []
        
        # 提取所有赋值
        assignments = defaultdict(list)
        
        # 模式：House X: value1, value2, ...
        house_pattern = r"[Hh]ouse\s+(\d+)[:：]\s*([^;\n]+)"
        matches = re.findall(house_pattern, response)
        
        for house_num, values_str in matches:
            values = [v.strip() for v in values_str.split(',')]
            assignments[f"House {house_num}"].extend(values)
        
        # 检查同一房子的多次赋值是否一致
        for entity, values_list in assignments.items():
            if len(values_list) > len(set(values_list)):
                # 有重复值，可能是多次赋值
                inconsistencies.append({
                    "type": "inconsistent_assignment",
                    "entity": entity,
                    "description": f"{entity} 被多次赋值，可能存在不一致",
                })
        
        return inconsistencies
    
    def _detect_duplicate_assignments(self, response: str) -> List[Dict]:
        """
        检测重复分配
        
        例如：同一属性被分配给多个实体
        """
        duplicates = []
        
        # 提取所有赋值
        assignments = defaultdict(list)
        
        # 模式：House X: value1, value2, ...
        house_pattern = r"[Hh]ouse\s+(\d+)[:：]\s*([^;\n]+)"
        matches = re.findall(house_pattern, response)
        
        # 构建属性到实体的映射
        attribute_to_entities = defaultdict(list)
        
        for house_num, values_str in matches:
            values = [v.strip() for v in values_str.split(',')]
            for value in values:
                attribute_to_entities[value.lower()].append(f"House {house_num}")
        
        # 检查重复
        for attr, entities in attribute_to_entities.items():
            if len(entities) > 1:
                duplicates.append({
                    "type": "duplicate_assignment",
                    "attribute": attr,
                    "entities": entities,
                    "description": f"属性 '{attr}' 被分配给多个实体: {', '.join(entities)}",
                })
        
        return duplicates
    
    def _generate_conflict_summary(self, conflicts: Dict[str, List[Dict]]) -> str:
        """生成冲突摘要"""
        if not any(conflicts.values()):
            return "未检测到逻辑冲突"
        
        summary_parts = []
        
        for conflict_type, conflict_list in conflicts.items():
            if conflict_list:
                summary_parts.append(f"{conflict_type}: {len(conflict_list)} 个")
        
        return "检测到以下冲突类型: " + ", ".join(summary_parts)
    
    async def generate_experience(
        self, 
        conflict_analysis: Dict[str, Any],
        question: str,
        response: str
    ) -> Optional[str]:
        """
        从冲突分析中生成经验总结
        
        Args:
            conflict_analysis: 冲突检测结果
            question: 原始问题
            response: 模型响应
            
        Returns:
            生成的经验字符串，如果LLM未配置则返回None
        """
        if not self.llm:
            logger.warning("LLM not configured, cannot generate experience")
            return None
        
        if not conflict_analysis["has_conflicts"]:
            return None
        
        # 准备提示
        system_prompt = """你是一个逻辑推理专家，擅长分析推理过程中的错误并提取经验教训。

你的任务是从逻辑冲突中提取有价值的经验，帮助改进未来的推理过程。

重点关注：
1. 冲突的根本原因
2. 如何避免类似的错误
3. 推理策略的改进建议
4. 系统化的检查方法

提供简洁、可操作的经验总结。"""
        
        # 格式化冲突信息
        conflicts_text = []
        for conflict_type, conflict_list in conflict_analysis["conflicts_by_type"].items():
            if conflict_list:
                conflicts_text.append(f"\n{conflict_type}:")
                for conflict in conflict_list[:3]:  # 最多3个示例
                    conflicts_text.append(f"  - {conflict.get('description', str(conflict))}")
        
        user_prompt = f"""分析以下逻辑推理中的冲突，并提取关键经验教训。

问题：
{question[:500]}

推理过程：
{response[:1000]}

检测到的冲突：
{''.join(conflicts_text)}

请生成1-3条简洁的经验总结，每条经验应该：
- 明确指出问题所在
- 提供可操作的改进建议
- 适用于类似的问题

经验总结："""
        
        try:
            experience = await self.llm.query_one(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
            )
            return experience.strip()
        except Exception as e:
            logger.error(f"Error generating experience: {e}")
            return None


async def analyze_sample(
    sample: EvaluationSample,
    detector: LogicConflictDetector,
    generate_experience: bool = True
) -> Dict[str, Any]:
    """分析单个样本"""
    # 检测冲突
    conflict_analysis = detector.detect_conflicts(sample)
    
    result = {
        "sample_id": getattr(sample, "id", None),
        "has_conflicts": conflict_analysis["has_conflicts"],
        "total_conflicts": conflict_analysis["total_conflicts"],
        "conflicts_by_type": conflict_analysis["conflicts_by_type"],
        "summary": conflict_analysis["summary"],
    }
    
    # 生成经验
    if generate_experience and conflict_analysis["has_conflicts"]:
        experience = await detector.generate_experience(
            conflict_analysis,
            sample.raw_question or "",
            sample.response or ""
        )
        result["experience"] = experience
    
    return result


async def main():
    parser = argparse.ArgumentParser(description="逻辑冲突检测和经验总结")
    parser.add_argument("--sample", type=str, help="单个样本JSON文件路径")
    parser.add_argument("--batch", type=str, help="批量样本JSON文件路径")
    parser.add_argument("--dataset", type=str, help="数据集名称（从数据库读取）")
    parser.add_argument("--limit", type=int, default=10, help="处理样本数量限制")
    parser.add_argument("--config", type=str, help="配置文件路径（用于LLM）")
    parser.add_argument("--no-experience", action="store_true", help="不生成经验总结")
    parser.add_argument("--output", type=str, help="输出文件路径")
    
    args = parser.parse_args()
    
    # 初始化LLM（如果配置了）
    llm = None
    if not args.no_experience and args.config:
        try:
            config = ConfigLoader.load_agent_config(args.config)
            llm = SimplifiedAsyncOpenAI(**config.model.model_provider.model_dump())
        except Exception as e:
            logger.warning(f"Failed to load LLM config: {e}")
    
    detector = LogicConflictDetector(llm=llm)
    
    # 加载样本
    samples = []
    
    if args.sample:
        with open(args.sample, 'r', encoding='utf-8') as f:
            sample_data = json.load(f)
            samples.append(EvaluationSample(**sample_data))
    
    elif args.batch:
        with open(args.batch, 'r', encoding='utf-8') as f:
            samples_data = json.load(f)
            samples = [EvaluationSample(**data) for data in samples_data[:args.limit]]
    
    elif args.dataset:
        # 从数据库读取（需要实现）
        logger.warning("Database reading not implemented yet")
        return
    
    else:
        parser.print_help()
        return
    
    # 分析样本
    results = []
    for sample in samples:
        result = await analyze_sample(
            sample, 
            detector, 
            generate_experience=not args.no_experience
        )
        results.append(result)
        
        # 打印结果
        print(f"\n样本 {len(results)}:")
        print(f"  冲突检测: {'有冲突' if result['has_conflicts'] else '无冲突'}")
        print(f"  冲突总数: {result['total_conflicts']}")
        print(f"  摘要: {result['summary']}")
        if 'experience' in result and result['experience']:
            print(f"  经验总结: {result['experience'][:200]}...")
    
    # 保存结果
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存到: {args.output}")
    
    # 统计信息
    total_conflicts = sum(r['total_conflicts'] for r in results)
    samples_with_conflicts = sum(1 for r in results if r['has_conflicts'])
    print(f"\n统计:")
    print(f"  总样本数: {len(results)}")
    print(f"  有冲突样本: {samples_with_conflicts}")
    print(f"  总冲突数: {total_conflicts}")


if __name__ == "__main__":
    asyncio.run(main())


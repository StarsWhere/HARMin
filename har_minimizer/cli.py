from __future__ import annotations

import argparse
import logging
import sys
from typing import Any, Dict, Optional

from .config import load_config
from .orchestrator import MinimizationOrchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HAR 请求最小化命令行工具")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("--input-har", dest="input_har", help="覆盖配置中的 HAR 输入路径")
    parser.add_argument("--output-har", dest="output_har", help="覆盖配置中的 HAR 输出路径")
    parser.add_argument("--report", dest="report_path", help="覆盖配置中的报告输出路径")
    parser.add_argument("--log-level", default="INFO", help="日志级别")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    overrides: Dict[str, Any] = {}
    if args.input_har:
        overrides["input_har"] = args.input_har
    if args.output_har:
        overrides["output_har"] = args.output_har
    if args.report_path:
        overrides["report_path"] = args.report_path
    config = load_config(args.config, overrides=overrides)
    orchestrator = MinimizationOrchestrator(config)
    orchestrator.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())

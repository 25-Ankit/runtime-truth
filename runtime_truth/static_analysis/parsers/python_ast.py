"""Parser for Python source code using the ast module."""

import ast
from pathlib import Path
from typing import List

from runtime_truth.core.enums import DeclaredEntityType
from runtime_truth.core.identifiers import generate_entity_id
from runtime_truth.core.models import DeclaredEntity, SourceLocation
from runtime_truth.static_analysis.base import StaticParser


class PythonAstParser(StaticParser):
    """Parses Python source files using AST to extract imports, environment accesses, and static paths."""

    def can_parse(self, file_path: Path) -> bool:
        return file_path.suffix.lower() == ".py"

    def parse(self, file_path: Path, run_id: str, project_root: Path) -> List[DeclaredEntity]:
        entities: List[DeclaredEntity] = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content, filename=str(file_path))
        except (SyntaxError, Exception):
            return entities

        try:
            rel_path = str(file_path.relative_to(project_root))
        except ValueError:
            rel_path = str(file_path)

        for node in ast.walk(tree):
            # 1. import foo, import foo.bar as fb
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top_module = alias.name.split(".")[0]
                    norm_name = top_module.lower().replace("_", "-")
                    entity_id = generate_entity_id(
                        DeclaredEntityType.DEPENDENCY.value,
                        norm_name,
                        qualifier=f"ast:{rel_path}:{node.lineno}",
                    )
                    entities.append(
                        DeclaredEntity(
                            entity_id=entity_id,
                            run_id=run_id,
                            entity_type=DeclaredEntityType.DEPENDENCY,
                            name=top_module,
                            normalized_value=norm_name,
                            raw_value=f"import {alias.name}" + (f" as {alias.asname}" if alias.asname else ""),
                            source=rel_path,
                            source_location=SourceLocation(
                                file_path=rel_path,
                                line_number=node.lineno,
                                column_number=node.col_offset,
                            ),
                            metadata={"full_import": alias.name, "syntax": "import"},
                        )
                    )

            # 2. from foo.bar import baz
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    top_module = node.module.split(".")[0]
                    norm_name = top_module.lower().replace("_", "-")
                    entity_id = generate_entity_id(
                        DeclaredEntityType.DEPENDENCY.value,
                        norm_name,
                        qualifier=f"ast:{rel_path}:{node.lineno}",
                    )
                    names_str = ", ".join(a.name for a in node.names)
                    entities.append(
                        DeclaredEntity(
                            entity_id=entity_id,
                            run_id=run_id,
                            entity_type=DeclaredEntityType.DEPENDENCY,
                            name=top_module,
                            normalized_value=norm_name,
                            raw_value=f"from {node.module} import {names_str}",
                            source=rel_path,
                            source_location=SourceLocation(
                                file_path=rel_path,
                                line_number=node.lineno,
                                column_number=node.col_offset,
                            ),
                            metadata={"full_import": node.module, "names": [a.name for a in node.names], "syntax": "from_import"},
                        )
                    )

            # 3. os.environ.get("KEY") or os.getenv("KEY")
            elif isinstance(node, ast.Call):
                func = node.func
                env_var_name = None
                # os.getenv("KEY")
                if isinstance(func, ast.Attribute) and func.attr == "getenv":
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        env_var_name = node.args[0].value
                # os.environ.get("KEY")
                elif isinstance(func, ast.Attribute) and func.attr == "get":
                    if isinstance(func.value, ast.Attribute) and func.value.attr == "environ":
                        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                            env_var_name = node.args[0].value

                if env_var_name:
                    entity_id = generate_entity_id(
                        DeclaredEntityType.ENVIRONMENT_VARIABLE.value, env_var_name
                    )
                    entities.append(
                        DeclaredEntity(
                            entity_id=entity_id,
                            run_id=run_id,
                            entity_type=DeclaredEntityType.ENVIRONMENT_VARIABLE,
                            name=env_var_name,
                            normalized_value=env_var_name,
                            raw_value=f"os.getenv('{env_var_name}')",
                            source=rel_path,
                            source_location=SourceLocation(
                                file_path=rel_path,
                                line_number=node.lineno,
                                column_number=node.col_offset,
                            ),
                            metadata={"syntax": "ast_env_call"},
                        )
                    )

            # 4. os.environ["KEY"]
            elif isinstance(node, ast.Subscript):
                if isinstance(node.value, ast.Attribute) and node.value.attr == "environ":
                    slice_node = node.slice
                    if isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, str):
                        env_var_name = slice_node.value
                        entity_id = generate_entity_id(
                            DeclaredEntityType.ENVIRONMENT_VARIABLE.value, env_var_name
                        )
                        entities.append(
                            DeclaredEntity(
                                entity_id=entity_id,
                                run_id=run_id,
                                entity_type=DeclaredEntityType.ENVIRONMENT_VARIABLE,
                                name=env_var_name,
                                normalized_value=env_var_name,
                                raw_value=f"os.environ['{env_var_name}']",
                                source=rel_path,
                                source_location=SourceLocation(
                                    file_path=rel_path,
                                    line_number=node.lineno,
                                    column_number=node.col_offset,
                                ),
                                metadata={"syntax": "ast_environ_subscript"},
                            )
                        )

        return entities

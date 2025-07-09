import re
from abc import ABC
from ast import literal_eval
from collections import defaultdict
from typing import Any, Dict, List, Literal, Optional, Set, Tuple, cast

from pydantic import BaseModel, ConfigDict

VISIBILITY_TYPES = Literal[
    "private", "protected", "package private", "package_private", "internal", "public"
]
NODE_TYPES = Literal["class", "variable", "function", "entity", "method", "field"]


def clean_id(data_id: str) -> str:
    return data_id.replace("()", "").replace(" ", "").strip()


class SubscriptableBaseModel(BaseModel):
    def __getitem__(self, key: Any) -> Any:
        return getattr(self, key)

    def __setitem__(self, key: Any, value: Any) -> None:
        return setattr(self, key, value)

    def get(self, key: Any, default: Any) -> Any:
        return getattr(self, key) if hasattr(self, key) else default

    def __str__(self):
        return str(self.model_dump(mode="json"))


class Node(SubscriptableBaseModel):
    type: NODE_TYPES
    name: str
    node_id: str
    description: Optional[str]
    visibility: VISIBILITY_TYPES
    return_type: Optional[str] = None
    params: Optional[str] = None
    source_class_id: Optional[str] = None


class Edge(SubscriptableBaseModel):
    node_id_from: str
    node_id_to: str
    description: Optional[str] = None


class Package(SubscriptableBaseModel):
    package_id: str
    children: List[str]
    description: Optional[str] = None


class Graph(SubscriptableBaseModel):
    nodes: List[Node]
    edges: List[Edge]
    packages: List[Package]


class GraphTemplate(ABC):
    def node_to_str(
        self,
        node: Node,
        methods: List[Node],
        fields: List[Node],
        hide_empty_members: bool,
    ) -> Optional[str]:
        if node.type in ("class", "entity"):
            fields_repr = [
                self.variable_template(
                    name=f.name, visibility=f.visibility, field_type=f.return_type
                )
                for f in fields
            ]
            methods_repr = [
                self.function_template(
                    name=m.name,
                    visibility=m.visibility,
                    return_type=m.return_type,
                    params=m.params,
                    description=m.description,
                )
                for m in methods
            ]
        elif node.type in ("function", "method"):
            fields_repr = []
            methods_repr = [
                self.function_template(
                    name=node.name,
                    visibility=node.visibility,
                    return_type=node.return_type,
                    params=node.params,
                    description=node.description,
                )
            ]
        elif node.type in ("variable", "field"):
            fields_repr = [
                self.variable_template(
                    name=node.name,
                    visibility=node.visibility,
                    field_type=node.return_type,
                )
            ]
            methods_repr = []
        else:
            return None

        return self.node_template(
            name=node.name,
            node_id=node.node_id,
            hide_empty_members=hide_empty_members,
            node_type=node.type,
            description=node.description,
            fields=fields_repr,
            methods=methods_repr,
        )

    def node_template(
        self,
        name: str,
        node_id: str,
        hide_empty_members: bool,
        node_type: NODE_TYPES,
        description: Optional[str],
        fields: List[str],
        methods: List[str],
    ) -> str:
        raise NotImplementedError()

    def edge_template(
        self, node_id_from: str, node_id_to: str, description: Optional[str] = None
    ) -> str:
        raise NotImplementedError()

    def package_template(self, package_id: str, content: str) -> str:
        raise NotImplementedError()

    def function_template(
        self,
        name: str,
        visibility: VISIBILITY_TYPES,
        return_type: Optional[str],
        params: Optional[str],
        description: Optional[str],
    ) -> str:
        raise NotImplementedError()

    def variable_template(
        self, name: str, visibility: VISIBILITY_TYPES, field_type: Optional[str]
    ) -> str:
        raise NotImplementedError()

    def diagram_template(self, content: str, hide_empty_members: bool):
        raise NotImplementedError()


class PlantUMLTemplate(GraphTemplate):
    def __init__(self):
        self.VISIBILITY_MAP: Dict[VISIBILITY_TYPES, str] = {
            cast(VISIBILITY_TYPES, "private"): "-",
            cast(VISIBILITY_TYPES, "protected"): "#",
            cast(VISIBILITY_TYPES, "package private"): "~",
            cast(VISIBILITY_TYPES, "package_private"): "~",
            cast(VISIBILITY_TYPES, "internal"): "~",
            cast(VISIBILITY_TYPES, "public"): "+",
        }

        self.NODE_TYPE_MAP: Dict[NODE_TYPES, str] = {
            cast(NODE_TYPES, "class"): "",
            cast(NODE_TYPES, "variable"): "<< (V,cyan) >>",
            cast(NODE_TYPES, "function"): "<< (F,orange) >>",
            cast(NODE_TYPES, "entity"): "<< (E,orchid) >>",
            cast(NODE_TYPES, "method"): "<< (M,tomato) >>",
            cast(NODE_TYPES, "field"): "<< (f,lightblue) >>",
        }

    def node_template(
        self,
        name: str,
        node_id: str,
        hide_empty_members: bool,
        node_type: NODE_TYPES,
        description: Optional[str],
        fields: List[str],
        methods: List[str],
    ) -> str:
        if name == node_id:
            template = [f"class {name} {self.NODE_TYPE_MAP[node_type]}" + "{"]
        else:
            template = [
                f'class "{name}" as {node_id} {self.NODE_TYPE_MAP[node_type]}' + "{"
            ]
        if description is not None and len(description) > 0:
            template.append(f"{description}")
            if not hide_empty_members or len(fields) > 0 or len(methods) > 0:
                template.append("--")
        if len(fields) > 0:
            template += fields
        if len(methods) > 0:
            template += methods
        template.append("}")
        return "\n".join(template)

    def edge_template(
        self, node_id_from: str, node_id_to: str, description: Optional[str] = None
    ) -> str:
        return (
            f'"{node_id_from}" --> "{node_id_to}"'
            if description is None or len(description) == 0
            else f'"{node_id_from}" --> "{node_id_to}" : "{description}"'
        )

    def package_template(self, package_id: str, content: str) -> str:
        return f"package {package_id}" + " {\n" + content + "\n}"

    def function_template(
        self,
        name: str,
        visibility: VISIBILITY_TYPES,
        return_type: Optional[str],
        params: Optional[str],
        description: Optional[str],
    ) -> str:
        return f"{self.VISIBILITY_MAP[visibility]}{name}({params}) : {return_type}"

    def variable_template(
        self, name: str, visibility: VISIBILITY_TYPES, field_type: Optional[str]
    ) -> str:
        assert field_type is not None
        return f"{self.VISIBILITY_MAP[visibility]}{field_type} {name}"

    def diagram_template(self, content: str, hide_empty_members: bool):
        return "\n".join(
            [
                "@startuml",
                "set separator none",
                *(["hide empty members"] if hide_empty_members else []),
                content,
                "@enduml",
            ]
        )


class MermaidJSTemplate(GraphTemplate):
    def __init__(self, enable_links: bool = False):
        self.VISIBILITY_MAP: Dict[VISIBILITY_TYPES, str] = {
            cast(VISIBILITY_TYPES, "private"): "-",
            cast(VISIBILITY_TYPES, "protected"): "#",
            cast(VISIBILITY_TYPES, "package private"): "~",
            cast(VISIBILITY_TYPES, "package_private"): "~",
            cast(VISIBILITY_TYPES, "internal"): "~",
            cast(VISIBILITY_TYPES, "public"): "+",
        }
        self.NODE_TYPE_MAP: Dict[NODE_TYPES, str] = {
            cast(NODE_TYPES, "class"): "",
            cast(NODE_TYPES, "variable"): "<<Variable>>",
            cast(NODE_TYPES, "function"): "<<Function>>",
            cast(NODE_TYPES, "entity"): "<<Entity>>",
            cast(NODE_TYPES, "method"): "<<Method>>",
            cast(NODE_TYPES, "field"): "<<Field>>",
        }
        self.enable_links = enable_links
        self.links = []

    def node_template(
        self,
        name: str,
        node_id: str,
        hide_empty_members: bool,
        node_type: NODE_TYPES,
        description: Optional[str],
        fields: List[str],
        methods: List[str],
    ) -> str:
        if name == node_id:
            template = [f"class {name}" + "{\n", f"{self.NODE_TYPE_MAP[node_type]}"]
        else:
            template = [
                f'class {node_id}["{name}"]' + "{\n",
                f"{self.NODE_TYPE_MAP[node_type]}",
            ]
        if description is not None and len(description) > 0:
            template.append(f"{description}")
            if not hide_empty_members or len(fields) > 0 or len(methods) > 0:
                template.append("--")
        if len(fields) > 0:
            template += fields
        if len(methods) > 0:
            template += methods
        template.append("}")
        if self.enable_links:
            self.links.append(f"click {name} href \"javascript:markNode('{name}')\"")
        return "\n".join(template)

    def edge_template(
        self, node_id_from: str, node_id_to: str, description: Optional[str] = None
    ) -> str:
        return (
            f"{node_id_from} --> {node_id_to}"
            if description is None or len(description) == 0
            else f"{node_id_from} --> {node_id_to} : {description}"
        )

    def package_template(self, package_id: str, content: str) -> str:
        return f"namespace {package_id}" + " {\n" + content + "\n}"

    def function_template(
        self,
        name: str,
        visibility: VISIBILITY_TYPES,
        return_type: Optional[str],
        params: Optional[str],
        description: Optional[str],
    ) -> str:
        return f"{self.VISIBILITY_MAP[visibility]}{name}({params}) {return_type}"

    def variable_template(
        self, name: str, visibility: VISIBILITY_TYPES, field_type: Optional[str]
    ) -> str:
        assert field_type is not None
        return f"{self.VISIBILITY_MAP[visibility]}{name} {field_type}"

    def diagram_template(self, content: str, hide_empty_members: bool):
        return "\n".join(
            [
                *(
                    ["---\nconfig:\n\tclass:\n\t\thideEmptyMembersBox: true\n---\n"]
                    if hide_empty_members
                    else []
                ),
                "classDiagram",
                content,
            ]
        )


class MermaidJSFlowchartTemplate(GraphTemplate):
    def __init__(self, enable_links: bool = False):
        self.VISIBILITY_MAP: Dict[VISIBILITY_TYPES, str] = {
            cast(VISIBILITY_TYPES, "private"): "-",
            cast(VISIBILITY_TYPES, "protected"): "#",
            cast(VISIBILITY_TYPES, "package private"): "~",
            cast(VISIBILITY_TYPES, "package_private"): "~",
            cast(VISIBILITY_TYPES, "internal"): "~",
            cast(VISIBILITY_TYPES, "public"): "+",
        }
        self.NODE_TYPE_MAP: Dict[NODE_TYPES, str] = {
            cast(NODE_TYPES, "class"): "baseClass",
            cast(NODE_TYPES, "variable"): "variable",
            cast(NODE_TYPES, "function"): "function",
            cast(NODE_TYPES, "entity"): "entity",
            cast(NODE_TYPES, "method"): "method",
            cast(NODE_TYPES, "field"): "field",
        }
        self.enable_links = enable_links
        self.links = []

    def node_template(
        self,
        name: str,
        node_id: str,
        hide_empty_members: bool,
        node_type: NODE_TYPES,
        description: Optional[str],
        fields: List[str],
        methods: List[str],
    ) -> str:
        template = [f'{node_id}["']
        node_content = [f"{name}"]
        if description is not None and len(description) > 0:
            node_content.append(f"{description}")
        if len(fields) > 0:
            node_content += fields
        if len(methods) > 0:
            node_content += methods
        template.append('<hr color="black"/>'.join(node_content))
        template.append(f'"]:::{self.NODE_TYPE_MAP[node_type]}')
        if self.enable_links:
            self.links.append(
                f"click {node_id} href \"javascript:markNode('{node_id}')\""
            )
        return "\n".join(template)

    def edge_template(
        self, node_id_from: str, node_id_to: str, description: Optional[str] = None
    ) -> str:
        return (
            f"{node_id_from} --> {node_id_to}"
            if description is None or len(description) == 0
            else f'{node_id_from} -- "{description}" --> {node_id_to}'
        )

    def package_template(self, package_id: str, content: str) -> str:
        return "\n".join(
            [
                f"subgraph {package_id}",
                *content.split("\n"),
                "end",
            ]
        )

    def function_template(
        self,
        name: str,
        visibility: VISIBILITY_TYPES,
        return_type: Optional[str],
        params: Optional[str],
        description: Optional[str],
    ) -> str:
        return f"{self.VISIBILITY_MAP[visibility]}{name}({params}) {return_type}"

    def variable_template(
        self, name: str, visibility: VISIBILITY_TYPES, field_type: Optional[str]
    ) -> str:
        assert field_type is not None
        return f"{self.VISIBILITY_MAP[visibility]}{name} {field_type}"

    def diagram_template(self, content: str, hide_empty_members: bool):
        return "\n".join(
            [
                "flowchart TB",
                *content.split("\n"),
                "classDef baseClass fill:lightgreen",
                "classDef variable fill:PaleTurquoise",
                "classDef function fill:PapayaWhip",
                "classDef entity fill:Thistle",
                "classDef method fill:Coral",
                "classDef field fill:lightblue",
            ]
        )


def generate_nodes_repr(
    nodes: List[Node],
    classes: Dict[str, Dict[str, List[Node]]],
    nodes_to_show: Set[str],
    hide_empty_members: bool,
    graph_template: GraphTemplate,
) -> Dict[str, str]:
    nodes_repr = {}
    for node in nodes:
        if node.node_id in nodes_to_show:
            methods = classes.get(node.node_id, {}).get("methods", [])
            fields = classes.get(node.node_id, {}).get("fields", [])
            cur_repr = graph_template.node_to_str(
                node, methods, fields, hide_empty_members
            )
            if cur_repr is not None:
                nodes_repr[node.node_id] = cur_repr
    return nodes_repr


def generate_edges_repr(
    graph: Dict[str, Dict[str, Optional[str]]],
    nodes_to_show: Set[str],
    graph_template: GraphTemplate,
) -> List[str]:
    edges_repr = [
        graph_template.edge_template(
            node_id_from=node_id_from, node_id_to=node_id_to, description=description
        )
        for node_id_from, children in graph.items()
        if node_id_from in nodes_to_show
        for node_id_to, description in children.items()
        if node_id_to in nodes_to_show
    ]
    return edges_repr


def generate_package_repr(
    package_graph: Dict[str, Set[str]],
    nodes_repr: Dict[str, str],
    graph_template: GraphTemplate,
) -> Dict[str, str]:
    package_repr = {}
    visited = set()

    def dfs(package_id: str) -> Optional[str]:
        if package_id in visited:
            # return None to avoid recursion
            return None
        visited.add(package_id)

        components_repr = []
        for component_id in package_graph[package_id]:
            if component_id in nodes_repr:
                components_repr.append(nodes_repr[component_id])
                del nodes_repr[component_id]
            elif component_id in package_graph:
                if component_id in package_repr:
                    components_repr.append(package_repr[component_id])
                    del package_repr[component_id]
                else:
                    cur_component_repr = dfs(component_id)
                    if cur_component_repr is not None:
                        components_repr.append(cur_component_repr)

        return graph_template.package_template(
            package_id=package_id, content="\n".join(components_repr)
        )

    for package_id in package_graph:
        if package_id not in visited:
            package_repr[package_id] = dfs(package_id)

    return package_repr


def process_graph(
    nodes: List[Node],
    graph: Dict[str, Dict[str, Optional[str]]],
    package_graph: Dict[str, Set[str]],
    outside_members: bool,
) -> Tuple[Dict[str, Dict[str, List[Node]]], Set[str]]:
    classes: Dict[str, Dict[str, List[Node]]] = defaultdict(lambda: defaultdict(list))
    nodes_to_show: Set[str] = set()

    reversed_graph: Dict[str, List[str]] = defaultdict(list)
    for node_id_from, children in graph.items():
        for node_id_to in children:
            reversed_graph[node_id_to].append(node_id_from)

    node_to_package: Dict[str, str] = {
        child_id: parent_id
        for parent_id, children in package_graph.items()
        for child_id in children
    }

    nodes_types: Dict[str, str] = {node.node_id: node.type for node in nodes}

    for node in nodes:
        if node.type in ("method", "field"):
            source_class_id = node.source_class_id
            node_pkg = node_to_package.get(node.node_id, None)

            if (
                source_class_id is not None
                and source_class_id in nodes_types
                and nodes_types[source_class_id] == "class"
            ):
                if not outside_members:
                    classes[source_class_id][f"{node.type}s"].append(node)
                    if node_pkg is not None:
                        package_graph[node_pkg].discard(node.node_id)
                    continue
                else:
                    class_pkg = node_to_package.get(source_class_id, None)
                    # show nodes with edges and in packages
                    if class_pkg is not None:
                        if node_pkg is None:
                            package_graph[class_pkg].add(node["node_id"])
                        else:
                            package_graph[class_pkg].add(node_pkg)
                            # to avoid recursion
                            package_graph[node_pkg].discard(class_pkg)

        nodes_to_show.add(node.node_id)

    if not outside_members:
        for source_class_id, members_dict in classes.items():
            for member in members_dict["methods"] + members_dict["fields"]:
                # attach all edges from members to parent class
                graph[source_class_id].update(graph[member.node_id])
                graph[member.node_id] = dict()

    return classes, nodes_to_show


class GraphConvertConfig(SubscriptableBaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    outside_members: bool = True
    hide_empty_members: bool = True
    graph_template: GraphTemplate = PlantUMLTemplate()


def convert_graph(
    generated_graph: Graph, graph_convert_config: GraphConvertConfig
) -> str:
    nodes = generated_graph.nodes
    edges = generated_graph.edges
    packages = generated_graph.packages

    package_graph: Dict[str, Set[str]] = {
        p.package_id: set(p.children) for p in packages
    }
    graph: Dict[str, Dict[str, Optional[str]]] = defaultdict(dict)

    for e in edges:
        graph[e.node_id_from][e.node_id_to] = e.description

    classes, nodes_to_show = process_graph(
        nodes=nodes,
        graph=graph,
        package_graph=package_graph,
        outside_members=graph_convert_config["outside_members"],
    )

    nodes_repr = generate_nodes_repr(
        nodes=nodes,
        classes=classes,
        nodes_to_show=nodes_to_show,
        hide_empty_members=graph_convert_config["hide_empty_members"],
        graph_template=graph_convert_config["graph_template"],
    )
    edges_repr = generate_edges_repr(
        graph=graph,
        nodes_to_show=nodes_to_show,
        graph_template=graph_convert_config["graph_template"],
    )
    package_repr = generate_package_repr(
        package_graph=package_graph,
        nodes_repr=nodes_repr,
        graph_template=graph_convert_config["graph_template"],
    )

    links = []

    if type(graph_convert_config.graph_template) is MermaidJSFlowchartTemplate:
        if graph_convert_config.graph_template.enable_links:
            links = graph_convert_config.graph_template.links

    result = graph_convert_config.graph_template.diagram_template(
        content="\n".join(
            [*nodes_repr.values(), *package_repr.values(), *edges_repr, *links]
        ),
        hide_empty_members=graph_convert_config["hide_empty_members"],
    )

    return result


def fix_format(generated_graph_dict: Dict[str, Any]) -> Dict[str, Any]:
    # modify fields
    nodes_ids_map = {
        node["node_id"]: clean_id(node["node_id"])
        for node in generated_graph_dict["nodes"]
    }
    packages_ids_map = {
        package["package_id"]: clean_id(package["package_id"])
        for package in generated_graph_dict["packages"]
    }
    ids_map = packages_ids_map | nodes_ids_map

    # update fields in the graph
    generated_graph_dict["nodes"] = [
        node | {"node_id": nodes_ids_map[node["node_id"]]}
        for node in generated_graph_dict["nodes"]
    ]
    generated_graph_dict["edges"] = [
        edge
        | {
            "node_id_from": nodes_ids_map[edge["node_id_from"]],
            "node_id_to": nodes_ids_map[edge["node_id_to"]],
        }
        for edge in generated_graph_dict["edges"]
        if edge["node_id_from"] in nodes_ids_map and edge["node_id_to"] in nodes_ids_map
    ]
    generated_graph_dict["packages"] = [
        package
        | {
            "package_id": packages_ids_map[package["package_id"]],
            "children": [
                ids_map[node_id]
                for node_id in package["children"]
                if node_id in ids_map
            ],
        }
        for package in generated_graph_dict["packages"]
        if packages_ids_map[package["package_id"]] not in nodes_ids_map
    ]

    return generated_graph_dict


def migration(generated_graph_str: str) -> str:
    generated_graph_str_clean = re.sub(
        r"(?<![a-zA-Z0-9_])null(?![a-zA-Z0-9_])", "None", generated_graph_str.strip()
    )
    generated_graph_dict = literal_eval(generated_graph_str_clean)

    generated_graph_dict_migrated = Graph(nodes=[], edges=[], packages=[])

    name_to_type = {
        node["name"]: node["type"] for node in generated_graph_dict["nodes"]
    }
    reversed_graph: Dict[str, List[str]] = defaultdict(list)

    for edge in generated_graph_dict["edges"]:
        reversed_graph[edge["name_to"]].append(edge["name_from"])
        generated_graph_dict_migrated.edges.append(
            Edge(
                node_id_from=edge["name_from"],
                node_id_to=edge["name_to"],
                description=edge.get("description", None),
            )
        )

    for node in generated_graph_dict["nodes"]:
        if node["type"] in ("method", "field"):
            classes_parents = [
                parent
                for parent in reversed_graph[node["name"]]
                if parent in name_to_type and name_to_type[parent] == "class"
            ]
            new_node = Node(
                type=node["type"],
                name=node["name"],
                node_id=node["name"],
                description=node.get("description", None),
                visibility=node["visibility"],
                return_type=node.get("return_type", None),
                params=node.get("params", None),
                source_class_id=(
                    classes_parents[0] if len(classes_parents) == 1 else None
                ),
            )
        else:
            new_node = Node(
                type=node["type"],
                name=node["name"],
                node_id=node["name"],
                description=node.get("description", None),
                visibility=node["visibility"],
                return_type=node.get("return_type", None),
                params=node.get("params", None),
                source_class_id=None,
            )
        generated_graph_dict_migrated.nodes.append(new_node)

    for package in generated_graph_dict["packages"]:
        generated_graph_dict_migrated.packages.append(
            Package(
                package_id=package["name"],
                children=package["children"],
                description=package.get("description", None),
            )
        )
    return str(generated_graph_dict_migrated)


def convert_str_graph(
    generated_graph_str: str, graph_convert_config: GraphConvertConfig
) -> str:
    generated_graph_str_clean = re.sub(
        r"(?<![a-zA-Z0-9_])null(?![a-zA-Z0-9_])", "None", generated_graph_str.strip()
    )
    generated_graph_dict = literal_eval(generated_graph_str_clean)
    generated_graph = Graph(**fix_format(generated_graph_dict))
    return convert_graph(generated_graph, graph_convert_config)


if __name__ == "__main__":
    graph = '{"nodes": [{"type": "function", "name": "crypto_hash_sha256_init", "node_id": "crypto_hash_sha256_init", "description": "Initializes SHA-256 hashing state", "visibility": "public", "return_type": "void", "params": "crypto_hash_sha256_state *state", "source_class_id": "crypto_hash_sha256_state"}, {"type": "function", "name": "crypto_hash_sha256_update", "node_id": "crypto_hash_sha256_update", "description": "Updates SHA-256 hash with input data", "visibility": "public", "return_type": "void", "params": "crypto_hash_sha256_state *state, const unsigned char *in, unsigned long long inlen", "source_class_id": "crypto_hash_sha256_state"}, {"type": "function", "name": "crypto_hash_sha256_final", "node_id": "crypto_hash_sha256_final", "description": "Finalizes SHA-256 hash calculation", "visibility": "public", "return_type": "void", "params": "crypto_hash_sha256_state *state, unsigned char *out", "source_class_id": "crypto_hash_sha256_state"}, {"type": "entity", "name": "crypto_hash_sha256_state", "node_id": "crypto_hash_sha256_state", "description": "State structure for SHA-256 hashing", "visibility": "public", "return_type": null, "params": null, "source_class_id": null}], "edges": [{"node_id_from": "crypto_hash_sha256_init", "node_id_to": "crypto_hash_sha256_state", "description": "initializes"}, {"node_id_from": "crypto_hash_sha256_update", "node_id_to": "crypto_hash_sha256_state", "description": "updates"}, {"node_id_from": "crypto_hash_sha256_final", "node_id_to": "crypto_hash_sha256_state", "description": "finalizes"}], "packages": [{"package_id": "hashing", "children": ["crypto_hash_sha256_init", "crypto_hash_sha256_update", "crypto_hash_sha256_final", "crypto_hash_sha256_state"], "description": "SHA-256 hashing functionality"}]}'
    print(
        convert_str_graph(
            graph,
            GraphConvertConfig(
                outside_members=True,
                hide_empty_members=True,
                graph_template=PlantUMLTemplate(),
            ),
        )
    )

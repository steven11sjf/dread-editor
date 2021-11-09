import re
import typing

import imgui
from mercury_engine_data_structures import dread_data


def render_bool(value, path: str):
    return imgui.checkbox(f"##{path}", value)


def render_float(value, path: str):
    return imgui.drag_float(f"##{path}", value)


def render_int(value, path: str):
    return imgui.drag_int(f"##{path}", value)


def render_string(value, path: str):
    return imgui.input_text(f"##{path}", value, 500)


def render_float_vector(value, path: str):
    functions = [None, None, imgui.input_float2, imgui.input_float3, imgui.input_float4]
    return functions[len(value)](f"##{path}", *value)


def render_typed_value(value, path: str):
    imgui.text(str(value))
    return False, value


KNOWN_TYPE_RENDERS: dict[str, typing.Callable[[typing.Any, str], tuple[bool, typing.Any]]] = {
    "bool": render_bool,
    "float": render_float,
    "float32": render_float,
    "int": render_int,
    "unsigned": render_int,
    "unsigned_int": render_int,

    "base::global::CStrId": render_string,
    "base::global::CFilePathStrId": render_string,
    "base::global::CRntString": render_string,
    "base::global::CName": render_string,
    "base::core::CAssetLink": render_string,
    "base::reflection::CTypedValue": render_typed_value,

    "base::math::CVector2D": render_float_vector,
    "base::math::CVector3D": render_float_vector,
    "base::math::CVector4D": render_float_vector,
}
vector_re = re.compile(r"(?:base::)?global::CRntVector<(.*?)(?:, false)?>$")
dict_re = re.compile(r"base::global::CRnt(?:Small)?Dictionary<base::global::CStrId,[\s_](.*)>$")
unique_ptr_re = re.compile(r"std::unique_ptr<(.*)>$")
weak_ptr_re = re.compile(r"base::global::CWeakPtr<(.*)>$")
raw_ptr_re = re.compile(r"(.*?)(?:[ ]?const)?\*$")
ref_re = re.compile(r"CGameObjectRef<(.*)>$")
typed_var_re = re.compile(r"(base::reflection::CTypedValue)$")
all_ptr_re = [unique_ptr_re, weak_ptr_re, raw_ptr_re, ref_re]


def find_ptr_match(type_name: str):
    for expr in all_ptr_re:
        m = expr.match(type_name)
        if m is not None:
            return m


def render_vector_of_type(value: list, type_name: str, path: str):
    modified = False
    single_column_element = type_uses_one_column(type_name)

    for i, item in enumerate(value):
        element_path = f"{path}[{i}]"
        changed, result = False, item

        if single_column_element:
            imgui.text(f"Item {i}")
            imgui.next_column()
            changed, result = render_value_of_type(item, type_name, element_path)
            imgui.next_column()
        else:
            node_open = imgui.tree_node(f"Item {i} ##{element_path}", imgui.TREE_NODE_DEFAULT_OPEN)
            if imgui.is_item_hovered():
                imgui.set_tooltip(type_name)

            if node_open:
                changed, result = render_value_of_type(item, type_name, element_path)
                imgui.tree_pop()
                imgui.next_column()
                imgui.next_column()

        if changed:
            value[i] = result
            modified = True

    with imgui.styled(imgui.STYLE_ALPHA, 0.5):
        imgui.button("New Item")
        imgui.next_column()
        imgui.text("(Not Implemented)")
        imgui.next_column()

    return modified, value


def render_dict_of_type(value: dict, type_name: str, path: str):
    modified = False
    for key, item in value.items():
        if imgui.tree_node(f"{key} ##{path}[{key}]"):
            changed, result = render_value_of_type(item, type_name, f"{path}[{key}]")
            if changed:
                value[key] = result
                modified = True
            imgui.tree_pop()

    with imgui.styled(imgui.STYLE_ALPHA, 0.5):
        imgui.button("New Item")
        imgui.next_column()
        imgui.text("(Not Implemented)")
        imgui.next_column()

    return modified, value


def render_ptr_of_type(value, type_name: str, path: str):
    if isinstance(value, dict) and "@type" in value:
        type_name = value["@type"]
    return render_value_of_type(value, type_name, path)


def type_uses_one_column(type_name: str):
    all_types: dict[str, typing.Any] = dread_data.get_raw_types()

    if type_name in KNOWN_TYPE_RENDERS:
        return True

    elif (m := vector_re.match(type_name)) is not None:
        return False

    elif (m := dict_re.match(type_name)) is not None:
        return False

    elif (m := find_ptr_match(type_name)) is not None:
        return False

    elif type_name in all_types:
        return all_types[type_name]["fields"] is not None

    else:
        return True


def render_enum_of_type(value, type_name: str, path: str) -> tuple[bool, typing.Any]:
    all_types: dict[str, typing.Any] = dread_data.get_raw_types()

    all_enum_values = list(all_types[type_name]["values"].keys())
    changed, selected = imgui.combo(path,
                                    all_enum_values.index(value),
                                    all_enum_values)
    if changed:
        return True, all_enum_values[selected]
    else:
        return False, value


def render_value_of_type(value, type_name: str, path: str) -> tuple[bool, typing.Any]:
    all_types: dict[str, typing.Any] = dread_data.get_raw_types()

    if type_name in KNOWN_TYPE_RENDERS:
        return KNOWN_TYPE_RENDERS[type_name](value, path)

    if value is None:
        # TODO
        imgui.text("None")
        return False, None

    if (m := vector_re.match(type_name)) is not None:
        return render_vector_of_type(value, m.group(1), path)

    if (m := dict_re.match(type_name)) is not None:
        return render_dict_of_type(value, m.group(1), path)

    if (m := find_ptr_match(type_name)) is not None:
        return render_ptr_of_type(value, m.group(1), path)

    if type_name not in all_types:
        imgui.next_column()
        imgui.text(f"Unsupported render of type {type_name}")
        imgui.next_column()
        return False, value

    this_type = all_types[type_name]

    if this_type.get("values") is not None:
        return render_enum_of_type(value, type_name, path)

    modified = False

    def render_type(type_data):
        nonlocal modified

        if type_data["parent"] is not None:
            render_type(all_types[type_data["parent"]])

        for field_name, field_type in type_data["fields"].items():
            imgui.checkbox(f"##{path}.{field_name}_present", field_name in value)
            imgui.same_line()

            changed, new_field = False, None

            if field_name in value:
                if type_uses_one_column(field_type):
                    imgui.text(field_name)
                    imgui.next_column()
                    if field_name in type_data.get("read_only_fields", []):
                        imgui.text(str(value[field_name]))
                    else:
                        changed, new_field = render_value_of_type(value[field_name], field_type,
                                                                  f"{path}.{field_name}")
                    imgui.next_column()

                else:
                    node_open = imgui.tree_node(f"{field_name} ##{path}.{field_name}", imgui.TREE_NODE_DEFAULT_OPEN)
                    if imgui.is_item_hovered():
                        imgui.set_tooltip(field_type)

                    if node_open:
                        changed, new_field = render_value_of_type(value[field_name], field_type,
                                                                  f"{path}.{field_name}")
                        imgui.tree_pop()

                    imgui.next_column()
                    imgui.next_column()
            else:
                imgui.text(field_name)
                imgui.next_column()
                imgui.text("<default>")
                imgui.next_column()

            if changed:
                value[field_name] = new_field
                modified = True

    if "@type" in value:
        imgui.text(f'Type: {value["@type"]}')
        imgui.next_column()
        imgui.next_column()

    render_type(all_types[type_name])
    return modified, value


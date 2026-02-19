import re
import shutil
from pathlib import Path


class ModelRegistryService:
    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)

    def resolve_models_dir(self, config_dir):
        models_dir = Path(config_dir, "models")
        models_dir.mkdir(parents=True, exist_ok=True)
        return models_dir

    def ensure_default_model_file(self, config_dir):
        config_dir = Path(config_dir)
        legacy_model_path = Path(config_dir, "model.task")
        models_dir = self.resolve_models_dir(config_dir)
        default_model_path = Path(models_dir, "default.task")
        if default_model_path.exists():
            return default_model_path

        bundled_model = Path(self.base_dir, "data", "model.task")
        source_model = legacy_model_path if legacy_model_path.exists() else bundled_model
        if source_model.exists():
            try:
                shutil.copy2(source_model, default_model_path)
                return default_model_path
            except Exception:
                return source_model
        return None

    def resolve_initial_model(self, config_dir):
        default_model_path = self.ensure_default_model_file(config_dir)
        if default_model_path and default_model_path.exists():
            return "Default", {"Default": str(default_model_path)}, default_model_path

        bundled_model = Path(self.base_dir, "data", "model.task")
        if bundled_model.exists():
            return "Default", {"Default": str(bundled_model)}, bundled_model

        fallback = Path(config_dir, "model.task")
        return "", {}, fallback

    def load_registry(self, config_dir, loaded_registry, selected_name):
        valid_registry = {}
        if isinstance(loaded_registry, dict):
            for name, path_str in loaded_registry.items():
                if not isinstance(name, str) or not name.strip():
                    continue
                if not isinstance(path_str, str) or not path_str.strip():
                    continue
                model_path = Path(path_str)
                if model_path.exists():
                    valid_registry[name.strip()] = str(model_path)

        if not valid_registry:
            default_model_path = self.ensure_default_model_file(config_dir)
            if default_model_path and default_model_path.exists():
                valid_registry = {"Default": str(default_model_path)}

        if isinstance(selected_name, str) and selected_name in valid_registry:
            resolved_name = selected_name
        elif valid_registry:
            resolved_name = next(iter(valid_registry.keys()))
        else:
            resolved_name = ""

        model_path = (
            Path(valid_registry[resolved_name])
            if resolved_name and resolved_name in valid_registry
            else Path(config_dir, "model.task")
        )
        return resolved_name, valid_registry, model_path

    def validate_model_name(self, name, existing_names):
        normalized = str(name or "").strip()
        if not normalized:
            return False, "Model name is invalid. Please try again."
        if len(normalized) > 64:
            return False, "Model name is invalid. Please try again."
        if not re.fullmatch(r"[A-Za-z0-9 _\-.]+", normalized):
            return False, "Model name is invalid. Please try again."
        existing_lower = {key.lower() for key in existing_names}
        if normalized.lower() in existing_lower:
            return False, "Model name is invalid. Please try again."
        return True, ""

    def import_model(self, config_dir, source_path, name, existing_names):
        source = Path(str(source_path or "")).expanduser()
        if not source.exists() or not source.is_file():
            return False, "Model file was not found.", None, None
        if source.suffix.lower() not in {".task", ".tasks"}:
            return (
                False,
                "Invalid model file. Please choose a .task or .tasks file.",
                None,
                None,
            )

        ok, message = self.validate_model_name(name, existing_names)
        if not ok:
            return False, message, None, None

        normalized_name = str(name).strip()
        models_dir = self.resolve_models_dir(config_dir)
        extension = source.suffix.lower()
        safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", normalized_name).strip("._")
        if not safe_stem:
            safe_stem = "model"

        destination = Path(models_dir, f"{safe_stem}{extension}")
        suffix_index = 2
        while destination.exists():
            destination = Path(models_dir, f"{safe_stem}_{suffix_index}{extension}")
            suffix_index += 1

        try:
            shutil.copy2(source, destination)
        except Exception:
            return False, "Failed to import model file.", None, None

        return True, "", normalized_name, destination

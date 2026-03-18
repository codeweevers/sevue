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

    def _bundled_model_path(self):
        return Path(self.base_dir, "data", "models", "default.task")

    def ensure_default_model_file(self, config_dir):
        config_dir = Path(config_dir)
        models_dir = self.resolve_models_dir(config_dir)
        default_model_path = Path(models_dir, "default.task")
        if default_model_path.exists():
            return default_model_path

        source_model = self._bundled_model_path()
        if source_model.exists():
            try:
                shutil.copy2(source_model, default_model_path)
                return default_model_path
            except Exception:
                return source_model
        return None

    def resolve_initial_model(self, config_dir):
        default_model_path = self.ensure_default_model_file(config_dir)
        if not default_model_path:
            model_path = self._bundled_model_path()
        if model_path and model_path.exists():
            return "Default", {"Default": str(model_path)}, model_path
        return "", {}, None

    def load_registry(self, config_dir, loaded_registry, selected_name):
        valid_registry = {}

        if isinstance(loaded_registry, dict):
            for name, path_str in loaded_registry.items():
                if not (isinstance(name, str) and isinstance(path_str, str)):
                    continue

                name = name.strip()
                path_str = path_str.strip()

                if not name or not path_str:
                    continue

                path = Path(path_str)
                if path.exists():
                    valid_registry[name] = str(path)

        if not valid_registry:
            default = self.ensure_default_model_file(config_dir)
            if default and default.exists():
                valid_registry = {"Default": str(default)}

        resolved_name = (
            selected_name
            if isinstance(selected_name, str) and selected_name in valid_registry
            else next(iter(valid_registry), "")
        )

        model_path = (
            Path(valid_registry[resolved_name])
            if resolved_name
            else Path(config_dir, "models", "default.task")
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

        if not (source.exists() and source.is_file()):
            return False, "Model file was not found.", None, None

        if source.suffix.lower() not in {".task"}:
            return (
                False,
                "Invalid model file. Please choose a .task file.",
                None,
                None,
            )

        ok, message = self.validate_model_name(name, existing_names)
        if not ok:
            return False, message, None, None

        models_dir = self.resolve_models_dir(config_dir)
        normalized_name = name.strip()

        safe_stem = (
            re.sub(r"[^A-Za-z0-9_.-]+", "_", normalized_name).strip("._") or "model"
        )
        extension = source.suffix.lower()

        destination = models_dir / f"{safe_stem}{extension}"
        i = 2
        while destination.exists():
            destination = models_dir / f"{safe_stem}_{i}{extension}"
            i += 1

        try:
            shutil.copy2(source, destination)
        except Exception:
            return False, "Failed to import model file.", None, None

        return True, "", normalized_name, destination

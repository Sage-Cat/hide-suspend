UUID := hide-suspend@sagecat.local
EXTENSION_DIR ?= $(HOME)/.local/share/gnome-shell/extensions/$(UUID)
FILES := metadata.json extension.js suspendAction.js buildInfo.js

.PHONY: check install uninstall

check:
	@jq -e '.uuid == "$(UUID)" and .["shell-version"] == ["46"]' metadata.json >/dev/null
	@node --input-type=module --check < extension.js
	@eslint extension.js suspendAction.js
	@node tests/lifecycle-static.mjs
	@echo "check: metadata, JavaScript syntax, ESLint, and lifecycle passed"

install: check
	install -d "$(EXTENSION_DIR)"
	install -m 0644 $(FILES) "$(EXTENSION_DIR)"
	@echo "Installed to $(EXTENSION_DIR)"

uninstall:
	rm -rf "$(EXTENSION_DIR)"

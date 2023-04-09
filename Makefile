all: chk_all

PY_FILES = $(shell find . -type f -name '*.py')
LINT_FILES = $(join $(dir $(PY_FILES)), $(patsubst %.py, .%.lint, $(notdir $(PY_FILES))))

.%.lint: %.py
	pylint $?
	@touch $@

chk_all: $(LINT_FILES)

clean:
	rm -f $(LINT_FILES)

ec:
	@echo $(PY_FILES)

.PHONY: all clean chk_all

# Working copy of the delivery report, kept on the Linux filesystem because
# pdflatex is ~10x faster here than on /mnt/c.  This copy is the one to edit;
# `make sync` mirrors it back into the repo (build/ excluded, main.pdf copied).
REPO ?= /mnt/c/Users/jazsa/Documents/Boost-Brigade
DEST := $(REPO)/0_Documentation/jared-assessment/CapstoneDelivery_latex

.PHONY: pdf tables figures sync clean

pdf:
	latexmk -pdf -outdir=build -interaction=nonstopmode -file-line-error -synctex=1 main.tex

tables:
	python3 tools/make_tables.py

figures:
	python3 tools/make_pv_shading.py

sync: pdf
	rsync -a --delete --exclude build/ --exclude .vscode/ ./ $(DEST)/
	mkdir -p $(DEST)/build && cp build/main.pdf $(DEST)/build/main.pdf

clean:
	latexmk -c -outdir=build main.tex

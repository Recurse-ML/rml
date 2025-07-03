# rml

Find bugs in code.
Using `rml` is as simple as changing a file, and running `rml <filename>`.
`rml` will analyze your changes for bugs and report them, if it has found any.

# Getting Started

## Installation

If you just want to use `rml` you can install it by running:

```bash
curl install.recurse.ml | sh
```

## Usage

_To run `rml` you need to be in a git repo_

Modify a local file and run:

```bash
rml funky/src/file.js
```

By default `rml` analyzes unstaged changes (i.e. the ones displayed by `git diff` without any arguments).

You can also specify the changes to compare against, by specifying `--from` and/or `--to` explicitly (they accept arbitrary git refs):

```bash
rml funky/src/file.js --from HEAD^

# or between branches
rml funky/src/file.js --to HEAD --head feat/chameleon
```

# Contributing

Contributions are welcome and highly appreciated.
This section describes how to set up your local environment for development.
If you run into any issues, reach out on [Discord](https://discord.gg/DHrYe75W), we're here to help🫡.

## Installation (dev)

From the project root, run:

```bash
make install
```

This will install Python 3.11.9 (using pyenv), uv, and all dependencies.

If you want to set up for development (with test/dev dependencies), run:

```bash
make install-dev
```

# Support

Having trouble? Check out the [existing issues](https://github.com/recurse-ml/rml/issues/) on GitHub, or feel free to open a new [one](https://github.com/recurse-ml/rml/issues/new/).

You can also ask for help on [Discord](https://discord.gg/DHrYe75W).

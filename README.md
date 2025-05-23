# rml

Find bugs in code.

At a high-level, using `rml` looks like:
1. Change a file.
2. Run `rml changed/file.py`.
3. Fix bugs identified by `rml`, repeat.



# Getting Started

## Installation

If you just want to use `rml` you can install by running: 

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

You can also specify the changes to compare against, by specifying `--base` and/or `--head` explicitly (they accept arbitrary git refs):

```bash
rml funky/src/file.js --base HEAD^

# or between branches
rml funky/src/file.js --base HEAD --head feat/chameleon
```

# Contributing

Contributions are welcome and highly appreciated.
This section describes how to set up your local environment for development.
If you run into any issues reach out on [Discord](https://discord.gg/DHrYe75W), we're here to help🫡.

## Installation (dev)

Ensure [UV](https://github.com/astral-sh/uv?tab=readme-ov-file#installation) is installed in your system:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then from project root run:

```bash
make install-test
```

# Support

Having trouble? Check out the [existing issues](https://github.com/recurse-ml/rml/issues/) on GitHub, or feel free to open a new one(https://github.com/recurse-ml/rml/issues/new/).

You can also ask for help on [Discord](https://discord.gg/DHrYe75W).

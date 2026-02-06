Installation
============

Requirements
------------

- Python 3.10+
- Rust toolchain

Clone And Install
-----------------

1. Clone the repository

.. code-block:: bash

   git clone <repo-url>
   cd jobscope

2. Install Rust (if not already installed)

.. code-block:: bash

   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

3. Install the package with pip

.. code-block:: bash

   pip install .

This builds the Rust worker via Maturin and installs the Python CLI.

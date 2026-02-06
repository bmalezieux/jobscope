Usage
=====

Local Monitoring
----------------

Monitor your local machine's resources in real-time.

.. code-block:: bash

   # Start interactive monitoring with default 2-second refresh
   jobscope

   # Custom refresh period (in seconds)
   jobscope --period 1.0

   # Run once and exit (no continuous monitoring)
   jobscope --once

   # Write a JSON summary on exit
   jobscope --summary ./metrics-summary.json

Press ``q`` to quit and clean up. Press ``Enter`` or ``Esc`` to toggle between global and per-node views.

Slurm Monitoring
----------------

Attach to a running Slurm job by ID.

.. code-block:: bash

   # Monitor a specific Slurm job
   jobscope --jobid 123456

   # Monitor with custom period and write a JSON summary on exit
   jobscope --jobid 123456 --period 5.0 --summary ./job_123456_summary.json

JobScope will wait for pending jobs to start, then run the monitoring worker
on the allocated compute nodes using ``srun`` while streaming metrics back
to your terminal.

Press ``q`` to quit and clean up. Press ``Enter`` or ``Esc`` to toggle between global and per-node views.
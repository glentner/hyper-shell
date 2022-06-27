Arguments
^^^^^^^^^

FIELD
    Select specific named fields to include in output.
    Default is to include all fields.

Options
^^^^^^^

``-w``, ``--where`` *COND...*
    List of conditional statements to filter results (e.g., ``-w 'exit_status != 0'``).

``-s``, ``--order-by`` *FIELD*
    Order results by field.

``-x``, ``--extract``
    Disable formatting for single column output.

``--json``
    Format output as JSON.

``--csv``
    Format output as CSV.

``-l``, ``--limit`` *NUM*
    Limit number of returned records.

``-c``, ``--count``
    Only print number of results that would be returned.
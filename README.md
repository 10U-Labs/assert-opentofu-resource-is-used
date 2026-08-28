# assert-opentofu-resource-is-used

Assert that every OpenTofu resource in a subsystem is reached by something.

## Why

A resource nothing references still deploys. It is planned, applied and
paid for on every deployment, it never does anything, and no tool in a
normal pipeline objects: `tofu validate` and `tflint` accept it, because
a resource with no dependents is legal OpenTofu and is frequently the
point of one. A DNS record and an email identity are reached by what
they publish rather than by an address.

So the question this asks is not "does anything reference it" but "is it
reached at all", and a resource is credited by four different kinds of
reach. Only a resource that fails all four is refused.

## Installation

```bash
pip install assert-opentofu-resource-is-used
```

## Usage

```bash
# One subsystem, crediting a use from anywhere in the repository
assert-opentofu-resource-is-used src/api/common/routing --search-in .

# Several subsystems at once
assert-opentofu-resource-is-used src/www/common src/bootstrap --search-in .
```

### Options

| Option | Effect |
| --- | --- |
| `--search-in PATH` | A tree to credit a use from, repeatable. Defaults to the directories themselves. |
| `--exclude PATTERNS` | Comma-separated globs to leave out. |
| `--annotate` | Print each finding as a GitHub Actions `::error` annotation. |
| `--quiet` | Print nothing; report through the exit code. |
| `--count` | Print only how many findings there were. |
| `--verbose` | Print the files read, the findings and a summary. |
| `--fail-fast` | Stop at the first finding. |
| `--warn-only` | Always exit 0. |

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Every resource is reached |
| 1 | A resource is reached by nothing |
| 2 | A directory was missing or a file was unreadable |

## What is read

Each directory argument is read for the `*.tf` files directly in it, and
nothing below it. A module directory beneath a subsystem is a namespace
of its own: nothing in the parent can interpolate an address inside it,
so pooling the two would credit a resource with a use that OpenTofu
could not resolve. Point the tool at a module directory to check the
module.

Every tree given to `--search-in` is walked for `.tf`, `.py`, `.yml`,
`.sh`, `.js` and `.ts` files, which are where the four credits below
live. Pass the whole repository: a remote state reader lives in another
subsystem, a `terraform_output` call under the tests, and a
`terraform output -raw` step in a workflow file.

## What counts as a use

A resource is refused only when all four of these hold at once.

### Nothing interpolates its address

`aws_dynamodb_table.events` written anywhere else in the directory is a
use, whether inside a string interpolation or in a bare expression.

An interpolation inside an `output` block is the exception, and it is
the trap this tool is built around. Exporting a resource is not using
it, so an interpolation there counts only when something reads that
output, and three things read one:

| Reader | Shape |
| --- | --- |
| Another subsystem's OpenTofu | `data.terraform_remote_state.x.outputs.name` |
| A test or a library, in Python | `terraform_output(directory, "name")` |
| A workflow step | `terraform output -raw name` |

A resource interpolated only by outputs nothing reads is refused along
with them.

### Its own body interpolates nothing of the directory

A resource attached at one end is attached. `aws_lambda_permission`
names the function it permits and `aws_iam_role_policy` names the role
it attaches to, and neither is named by anything in turn. So a body that
interpolates another resource, a data source or a module of the same
directory is a use, and only a body naming nothing but `local`, `var`
and literals can be refused.

### No string it assigns is spelled again

This is attachment by value rather than by address. An SES identity
declared as `email = "contact@${local.domain_name}"` is what makes a
policy condition and an environment variable spelling that same address
work, and nothing interpolates the identity. So every string a top-level
attribute of the block is assigned is looked for verbatim elsewhere in
the directory's `.tf` files, and finding one is a use.

### No program names its identifier

A resource can be reached from outside OpenTofu entirely, an SSM
parameter read at runtime by name being the usual case. The literal
parts of the identity attribute, split on the `${...}` interpolations,
are looked for in every `.py`, `.yml`, `.sh`, `.js` and `.ts` file in
the searched trees, and finding one is a use.

The identity attributes are a closed list: `alarm_name`, `alias`,
`bucket`, `domain_name`, `email`, `function_name`, `group_name`,
`identifier`, `key`, `log_group_name`, `name`, `parameter_name`,
`policy_name`, `queue_name`, `repository_name`, `role_name`,
`rule_name`, `stage_name`, `statement_id`, `table_name`, `topic_name`,
`trail_name`, `user_name` and `vault_name`. A resource type that spells
its identifier some other way is refused rather than credited, which is
a red run answered by adding the spelling.

## GitHub Actions

```yaml
- name: Assert every OpenTofu resource is used
  uses: 10U-Labs/assert-opentofu-resource-is-used@latest
  with:
    directories: src/api/common/routing
    search-in: .
```

`annotate` defaults to true there, so each finding lands on the line it
names in the diff.

## License

Apache-2.0

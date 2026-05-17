import type { ArgSpec, GroupSpec } from './models';
import {
  RunSpecError,
  formatMissingRequired,
  formatGroupExclusive,
  formatGroupInclusive,
  formatGroupAtLeastOne,
  formatGroupExactlyOne,
  formatDeprecated,
} from './errors';

export function validateArgs(parsedValues: Record<string, unknown>, argSpecs: Record<string, ArgSpec>): string[] {
  const errors: string[] = [];

  for (const [name, spec] of Object.entries(argSpecs)) {
    const value = parsedValues[name];
    const missing = value === null || value === undefined;

    if (spec.required && missing) {
      errors.push(formatMissingRequired(name, spec as unknown as Record<string, unknown>));
      continue;
    }

    if (!missing && spec.deprecated) {
      process.stderr.write(formatDeprecated(name, spec.deprecated) + '\n');
    }
  }

  return errors;
}

export function validateGroups(parsedValues: Record<string, unknown>, groupSpecs: Record<string, GroupSpec>): string[] {
  const errors: string[] = [];

  for (const [groupName, group] of Object.entries(groupSpecs)) {
    const groupArgs = group.args ?? [];
    const provided = groupArgs.filter((a) => parsedValues[a] !== null && parsedValues[a] !== undefined);

    if (group.exclusive && provided.length > 1) {
      errors.push(formatGroupExclusive(groupName, provided));
    } else if (group.inclusive && provided.length > 0 && provided.length < groupArgs.length) {
      errors.push(formatGroupInclusive(groupName, groupArgs.filter((a) => !provided.includes(a))));
    } else if (group.atLeastOne && provided.length === 0) {
      errors.push(formatGroupAtLeastOne(groupName, groupArgs));
    } else if (group.exactlyOne && provided.length !== 1) {
      errors.push(formatGroupExactlyOne(groupName, groupArgs, provided));
    } else if (group.condition) {
      const condVal = parsedValues[group.condition];
      if (condVal !== null && condVal !== undefined) {
        const requires = group.requires ?? [];
        const missing = requires.filter((a) => parsedValues[a] === null || parsedValues[a] === undefined);
        if (missing.length > 0) errors.push(formatGroupInclusive(groupName, missing));
      }
    }
  }

  return errors;
}

export function raiseIfErrors(errorMessages: string[]): void {
  if (errorMessages.length > 0) {
    throw new RunSpecError(errorMessages.join('\n\n'));
  }
}

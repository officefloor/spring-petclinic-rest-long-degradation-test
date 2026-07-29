package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import tools.jackson.databind.node.ObjectNode;

/**
 * cp05: duplicate detection ignores letter case. (The spec also mentions
 * surrounding/repeated whitespace, but the base app's letters-only name pattern
 * rejects padded names with 400 before dedup, so we assert the case dimension,
 * which is unambiguous and base-valid.)
 */
@Tag("cp05")
class Cp05Tests extends AcceptanceBase {

	@Test
	void coreUpperCaseHouseholdDuplicate() throws Exception {
		ObjectNode a = ownerNode();
		String last = a.get("lastName").asText();
		String phone = a.get("telephone").asText();
		createOwnerOk(a);
		ObjectNode b = ownerNode();
		b.put("lastName", last.toUpperCase()); // same surname, upper-cased
		b.put("telephone", phone);             // same telephone -> household duplicate
		createOwner(b).andExpect(status().isConflict());
	}

	@Test
	void functionalityLowerCaseHouseholdDuplicate() throws Exception {
		ObjectNode a = ownerNode();
		String last = a.get("lastName").asText();
		String phone = a.get("telephone").asText();
		createOwnerOk(a);
		ObjectNode b = ownerNode();
		b.put("lastName", last.toLowerCase()); // same surname, lower-cased
		b.put("telephone", phone);
		createOwner(b).andExpect(status().isConflict());
	}
}

package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.node.ObjectNode;

/** cp05: duplicate detection ignores case and surrounding/repeated whitespace. */
@Tag("cp05")
class Cp05Tests extends AcceptanceBase {

	@Test
	void coreCaseInsensitiveHouseholdDuplicate() throws Exception {
		ObjectNode a = ownerNode();
		String last = a.get("lastName").asText();
		String phone = a.get("telephone").asText();
		createOwnerOk(a);
		ObjectNode b = ownerNode();
		b.put("lastName", last.toUpperCase()); // same last name, different case
		b.put("telephone", phone);             // same telephone -> household duplicate
		createOwner(b).andExpect(status().isConflict());
	}

	@Test
	void functionalityWhitespaceInsensitiveDuplicate() throws Exception {
		ObjectNode a = ownerNode();
		String last = a.get("lastName").asText();
		String phone = a.get("telephone").asText();
		createOwnerOk(a);
		ObjectNode b = ownerNode();
		b.put("lastName", "  " + last + "  "); // same last name, padded whitespace
		b.put("telephone", phone);
		createOwner(b).andExpect(status().isConflict());
	}
}

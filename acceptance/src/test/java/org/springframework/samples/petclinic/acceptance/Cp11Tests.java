package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import tools.jackson.databind.node.ObjectNode;

/** cp11: telephone stored digits-only, and normalized before the uniqueness check. */
@Tag("cp11")
class Cp11Tests extends AcceptanceBase {

	private String formatted(String digits) {
		return "(" + digits.substring(0, 3) + ") " + digits.substring(3, 6) + "-" + digits.substring(6);
	}

	@Test
	void coreStoresDigitsOnly() throws Exception {
		String digits = uniqueTelephone();
		ObjectNode o = ownerNode();
		o.put("telephone", formatted(digits));
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.telephone").value(digits));
	}

	@Test
	void functionalityNormalisedDuplicateRejected() throws Exception {
		String digits = uniqueTelephone();
		ObjectNode a = ownerNode();
		a.put("telephone", digits);
		createOwnerOk(a);
		ObjectNode b = ownerNode();
		b.put("telephone", formatted(digits)); // same digits, punctuation added
		createOwner(b).andExpect(status().isConflict());
	}
}

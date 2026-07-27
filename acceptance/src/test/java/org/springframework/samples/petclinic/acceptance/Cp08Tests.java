package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.node.ObjectNode;

/** cp08: reject creating an owner with a telephone already in use (409). */
@Tag("cp08")
class Cp08Tests extends AcceptanceBase {

	@Test
	void coreRejectsDuplicateTelephone() throws Exception {
		String phone = uniquePhone();
		ObjectNode a = validOwner();
		a.put("telephone", phone);
		createOwnerOk(a);
		ObjectNode b = validOwner();
		b.put("telephone", phone);
		createOwner(b).andExpect(status().isConflict());
	}

	@Test
	void functionalityAllowsDistinctTelephone() throws Exception {
		createOwnerOk(validOwner());
		createOwner(validOwner()).andExpect(status().is2xxSuccessful());
	}

	@Test
	void functionalityTreatsNormalisedDuplicateAsConflict() throws Exception {
		String phone = uniquePhone(); // 10 digits, e.g. 6100000042
		ObjectNode a = validOwner();
		a.put("telephone", phone);
		createOwnerOk(a);
		ObjectNode b = validOwner();
		b.put("telephone", formatted(phone)); // same digits, punctuation added
		createOwner(b).andExpect(status().isConflict());
	}

	private String formatted(String digits) {
		return "(" + digits.substring(0, 3) + ") " + digits.substring(3, 6) + "-" + digits.substring(6);
	}
}

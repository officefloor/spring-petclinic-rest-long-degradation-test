package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.node.ObjectNode;

/** cp13: email must be unique when present (409). */
@Tag("cp13")
class Cp13Tests extends AcceptanceBase {

	@Test
	void coreRejectsDuplicateEmail() throws Exception {
		String email = uniqueEmail();
		ObjectNode a = validOwner();
		a.put("email", email);
		createOwnerOk(a);
		ObjectNode b = validOwner();
		b.put("email", email);
		createOwner(b).andExpect(status().isConflict());
	}

	@Test
	void functionalityAllowsDistinctEmails() throws Exception {
		ObjectNode a = validOwner();
		a.put("email", uniqueEmail());
		createOwnerOk(a);
		ObjectNode b = validOwner();
		b.put("email", uniqueEmail());
		createOwner(b).andExpect(status().is2xxSuccessful());
	}
}

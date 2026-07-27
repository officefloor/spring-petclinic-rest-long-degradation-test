package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.node.ObjectNode;

/** cp07: address required, not whitespace-only. */
@Tag("cp07")
class Cp07Tests extends AcceptanceBase {

	@Test
	void coreRejectsWhitespaceAddress() throws Exception {
		ObjectNode o = validOwner();
		o.put("address", "   ");
		createOwner(o).andExpect(status().isBadRequest());
	}

	@Test
	void errorRejectsMissingAddress() throws Exception {
		ObjectNode o = validOwner();
		o.remove("address");
		createOwner(o).andExpect(status().isBadRequest());
	}

	@Test
	void functionalityAcceptsValidAddress() throws Exception {
		createOwner(validOwner()).andExpect(status().is2xxSuccessful());
	}
}

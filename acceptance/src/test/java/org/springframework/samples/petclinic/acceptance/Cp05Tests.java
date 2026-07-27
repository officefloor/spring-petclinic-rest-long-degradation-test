package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.node.ObjectNode;

/** cp05: first and last name at most 50 characters. */
@Tag("cp05")
class Cp05Tests extends AcceptanceBase {

	@Test
	void coreRejectsFirstNameOver50() throws Exception {
		ObjectNode o = validOwner();
		o.put("firstName", "A".repeat(51));
		createOwner(o).andExpect(status().isBadRequest());
	}

	@Test
	void errorRejectsLastNameOver50() throws Exception {
		ObjectNode o = validOwner();
		o.put("lastName", "B".repeat(51));
		createOwner(o).andExpect(status().isBadRequest());
	}

	@Test
	void functionalityAcceptsExactly50() throws Exception {
		ObjectNode o = validOwner();
		o.put("firstName", "C".repeat(50));
		createOwner(o).andExpect(status().is2xxSuccessful());
	}
}
